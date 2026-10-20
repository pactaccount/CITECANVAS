"""Source-scoped runtime connecting saved PDFs to real retrieval and visual QA."""
import difflib
import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

import httpx
import numpy as np
from backend.src.retrieval.bm25_indexer import BM25Retriever
from backend.src.reasoning.vlm_client import VLMClient
from backend.src.reasoning.grounding import GroundingEngine
from backend.src.reasoning.abstention_guard import AbstentionGuard
from backend.src.observability import span


def load_environment(root):
    path = Path(root) / '.env'
    if path.exists():
        for line in path.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                if re.fullmatch(r'[A-Z][A-Z0-9_]*', key.strip()):
                    os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


class Runtime:
    def __init__(self, storage, catalog, native_lock=None):
        self.storage = Path(storage)
        self.catalog = catalog
        self.native_lock = native_lock or threading.RLock()
        self.model_lock = threading.BoundedSemaphore(2)
        self.index_lock = threading.Lock()
        self.embedding_model = os.getenv('EVID_EMBEDDING_MODEL', 'nvidia/llama-nemotron-embed-vl-1b-v2')
        self.qdrant_indexes_ready = set()
        self.last = {}

    def health(self):
        from urllib.parse import urlsplit
        return {'modelConfigured': bool(os.getenv('VLM_API_KEY')), 'provider': urlsplit(os.getenv('VLM_BASE_URL', 'https://integrate.api.nvidia.com/v1')).hostname,
                'model': os.getenv('VLM_MODEL_NAME', 'nvidia/qwen2.5-vl-7b-instruct'),
                'embeddingModel': self.embedding_model, 'qdrantConfigured': bool(os.getenv('QDRANT_URL')),
                'lastChecks': self.last, 'retrieval': 'BM25 + trained image embeddings; Qdrant with local vector fallback'}

    def clear_workspace_cache(self):
        """Remove derived vectors when an anonymous workspace is cleared.

        Uploaded source objects are removed by the storage backend. This takes
        care of retrieval artifacts, which are safe to regenerate but must not
        remain searchable after the source workspace is gone.
        """
        shutil.rmtree(self.storage.parent / 'rag_vectors', ignore_errors=True)
        if not os.getenv('QDRANT_URL'):
            return
        try:
            from qdrant_client import QdrantClient, models
            collection = os.getenv('EVID_QDRANT_COLLECTION', 'evid_runtime_pages_v1')
            namespace = hashlib.sha256(str(self.storage.resolve()).encode()).hexdigest()
            client = QdrantClient(url=os.environ['QDRANT_URL'], api_key=os.getenv('QDRANT_API_KEY'), timeout=20)
            if client.collection_exists(collection):
                client.delete(
                    collection_name=collection,
                    points_selector=models.FilterSelector(filter=models.Filter(must=[
                        models.FieldCondition(key='workspace', match=models.MatchValue(value=namespace))
                    ])),
                    wait=True,
                )
            client.close()
        except Exception:
            # Clear is still safe if the vector service is temporarily down:
            # its opaque workspace filter prevents those vectors from being
            # returned to any later workspace, and expiry/retry can remove it.
            pass

    def sources(self, ids):
        if not isinstance(ids, list) or not 1 <= len(ids) <= 8 or any(not isinstance(i, str) or not re.fullmatch('[a-f0-9]{64}', i) for i in ids):
            raise ValueError('Select between 1 and 8 uploaded PDFs.')
        records = {r['docId']: r for r in self.catalog()}
        if any(i not in records for i in ids):
            raise ValueError('A selected file is no longer available. Refresh Documents.')
        return [records[i] for i in dict.fromkeys(ids)]

    def evidence_page(self, source, page):
        """Create a lossless page only for final visual verification.

        Uploads persist compact previews. The original PDF is retained, and
        this cached 300-DPI render is used for model evidence and crops so a
        faster upload never reduces answer-verification fidelity.
        """
        from backend.src.ingestion.pdf_renderer import DocumentIngestionService

        document_dir = self.storage / source['docId']
        target = document_dir / f'page_{page}_evidence.png'
        if target.is_file():
            return target
        source_pdf = document_dir / 'source.pdf'
        if not source_pdf.is_file():
            raise FileNotFoundError('Original PDF is not available for visual verification.')
        with self.native_lock:
            return DocumentIngestionService.render_evidence_page(source_pdf, page, target)

    def embeddings(self, inputs, kind='passage', modality='image'):
        if not os.getenv('VLM_API_KEY'):
            raise RuntimeError('The server needs VLM_API_KEY to use NVIDIA analysis.')
        with span("evid.nvidia.embeddings", {"evid.input_count": len(inputs), "evid.input_kind": kind, "evid.modality": modality}):
            with httpx.Client(timeout=60) as client:
                response = client.post(os.getenv('VLM_BASE_URL', 'https://integrate.api.nvidia.com/v1').rstrip('/') + '/embeddings',
                    headers={'Authorization': 'Bearer ' + os.environ['VLM_API_KEY']},
                    json={'model': self.embedding_model, 'input': inputs, 'input_type': kind, 'modality': modality, 'encoding_format': 'float', 'truncate': 'END'})
        if response.status_code != 200:
            self.last['embeddings'] = {'status': 'unavailable', 'http': response.status_code}
            raise RuntimeError('Semantic indexing is unavailable; keyword retrieval remains available.')
        vectors = sorted(response.json()['data'], key=lambda d: d.get('index', 0))
        if len(vectors) != len(inputs):
            raise RuntimeError('The embedding provider returned an incomplete batch.')
        self.last['embeddings'] = {'status': 'connected', 'checkedAt': time.time()}
        return [v['embedding'] for v in vectors]

    def _qdrant_pages(self, source, query_vector):
        """Return existing document vectors without re-uploading them."""
        if not os.getenv('QDRANT_URL'):
            return []
        from qdrant_client import QdrantClient, models

        collection = os.getenv('EVID_QDRANT_COLLECTION', 'evid_runtime_pages_v1')
        namespace = hashlib.sha256(str(self.storage.resolve()).encode()).hexdigest()
        client = QdrantClient(url=os.environ['QDRANT_URL'], api_key=os.getenv('QDRANT_API_KEY'), timeout=20)
        try:
            if not client.collection_exists(collection):
                return []
            found = client.query_points(
                collection_name=collection,
                query=query_vector,
                query_filter=models.Filter(must=[
                    models.FieldCondition(key='workspace', match=models.MatchValue(value=namespace)),
                    models.FieldCondition(key='doc_id', match=models.MatchValue(value=source['docId'])),
                ]),
                limit=4,
            ).points
            return [int(point.payload['page']) for point in found]
        finally:
            client.close()

    def _ensure_qdrant_indexes(self, client, collection):
        """Create tenant filters once per runtime rather than per question."""
        if collection in self.qdrant_indexes_ready:
            return
        from qdrant_client import models
        indexed_fields = client.get_collection(collection).payload_schema or {}
        for field_name in ('workspace', 'doc_id'):
            if field_name not in indexed_fields:
                client.create_payload_index(
                    collection,
                    field_name=field_name,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                    wait=True,
                )
        self.qdrant_indexes_ready.add(collection)

    def semantic(self, source, query):
        cache_dir = self.storage.parent / 'rag_vectors'
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256((source['docId'] + self.embedding_model).encode()).hexdigest()
        cache = cache_dir / (key + '.json')
        query_vector = self.embeddings([query], 'query', 'text')[0]
        # A prior question may already have persisted the document vectors in
        # Qdrant. Query them first; the old path re-upserted every page for
        # each request, which added avoidable network latency.
        if os.getenv('QDRANT_URL'):
            try:
                found = self._qdrant_pages(source, query_vector)
                if found:
                    self.last['qdrant'] = {'status': 'reused', 'checkedAt': time.time()}
                    return found
            except Exception as error:
                self.last['qdrant'] = {'status': 'local_fallback', 'checkedAt': time.time(), 'error': type(error).__name__}
        with self.index_lock:
            if cache.exists():
                vectors = json.loads(cache.read_text())
            else:
                # Lazy indexing: upload itself remains local. Analysis explicitly invokes cloud processing.
                if source['totalPages'] > 120:
                    raise RuntimeError('Semantic indexing is limited to 120 pages per file; using keyword retrieval.')
                vectors = []
                for start in range(1, source['totalPages'] + 1, 2):
                    # Visual fallback retains the historic high-resolution
                    # evidence source. Preview images accelerate upload only;
                    # they are never substituted for visual semantic evidence.
                    images = ['data:image/jpeg;base64,' + VLMClient.encode_image_base64(self.evidence_page(source, p), max_dim=768)
                              for p in range(start, min(source['totalPages'] + 1, start + 2))]
                    vectors.extend(self.embeddings(images))
                temp = cache.with_suffix('.tmp')
                temp.write_text(json.dumps(vectors)); temp.replace(cache)
        if os.getenv('QDRANT_URL'):
            try:
                from qdrant_client import QdrantClient, models
                # Dedicated collection; no existing user collections are modified.
                collection = os.getenv('EVID_QDRANT_COLLECTION', 'evid_runtime_pages_v1')
                namespace = hashlib.sha256(str(self.storage.resolve()).encode()).hexdigest()
                client = QdrantClient(url=os.environ['QDRANT_URL'], api_key=os.getenv('QDRANT_API_KEY'), timeout=20)
                if not client.collection_exists(collection):
                    client.create_collection(collection, vectors_config=models.VectorParams(size=len(query_vector), distance=models.Distance.COSINE))
                self._ensure_qdrant_indexes(client, collection)
                client.upsert(collection, points=[models.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL, namespace+key+str(p))), vector=v,
                    payload={'workspace': namespace, 'doc_id': source['docId'], 'page': p}) for p, v in enumerate(vectors, 1)], wait=True)
                found = client.query_points(collection, query=query_vector, query_filter=models.Filter(must=[
                    models.FieldCondition(key='workspace', match=models.MatchValue(value=namespace)),
                    models.FieldCondition(key='doc_id', match=models.MatchValue(value=source['docId']))]), limit=4).points
                client.close()
                self.last['qdrant'] = {'status': 'connected', 'checkedAt': time.time()}
                return [int(p.payload['page']) for p in found]
            except Exception as error:
                self.last['qdrant'] = {
                    'status': 'local_fallback',
                    'checkedAt': time.time(),
                    'error': type(error).__name__,
                    'detail': str(error)[:160],
                }
        q = np.array(query_vector)
        scores = [float(np.dot(q,v)/(max(np.linalg.norm(q)*np.linalg.norm(v),1e-10))) for v in vectors]
        return sorted(range(1,len(vectors)+1), key=lambda p:scores[p-1], reverse=True)[:4]

    def retrieve(self, sources, query, *, include_semantic=True):
        candidates = []; warnings = []
        for source in sources:
            texts = {int(k): v for k,v in source.get('pageText', {}).items() if v.strip()}
            protected = re.findall(r'\b(?:lot|batch|part)\s*(?:number\s*)?[:#]?\s*([A-Za-z0-9-]*\d[A-Za-z0-9-]*)', query, re.I)
            if texts and protected and any(re.sub(r'\W','',p).lower() not in re.sub(r'\W','', ' '.join(texts.values())).lower() for p in protected):
                continue
            lexical = BM25Retriever(texts).retrieve(query, top_k=4) if texts else []
            ranks = {}
            for item in lexical:ranks[item['page_number']] = 2/(60+item['rank'])
            if include_semantic:
                try:
                    for rank, page in enumerate(self.semantic(source, query),1):ranks[page] = ranks.get(page,0)+1/(60+rank)
                except Exception as error:
                    warnings.append(str(error) if isinstance(error, RuntimeError) else 'Semantic retrieval unavailable; keyword retrieval used.')
            if not ranks and include_semantic:
                ranks = {p:0 for p in range(1,min(source['totalPages'],2)+1)}
            for page,score in sorted(ranks.items(), key=lambda x:x[1], reverse=True)[:2]:
                candidates.append((score, source, page))
        return sorted(candidates,key=lambda x:x[0],reverse=True)[:4], list(dict.fromkeys(warnings))

    def ask(self, ids, query):
        if not isinstance(query,str) or not 1 <= len(query.strip()) <= 2000:
            raise ValueError('Enter a question of up to 2,000 characters.')
        sources = self.sources(ids)
        if not os.getenv('VLM_API_KEY'):raise RuntimeError('NVIDIA analysis is not configured on this server.')
        started = time.perf_counter()
        # A text-backed page is cheap to locate and still receives the same
        # high-resolution visual verification. Only if that direct route
        # cannot establish an answer do we invoke visual semantic retrieval.
        candidates, warnings = self.retrieve(sources, query, include_semantic=False)
        fast_retrieval_ms = round((time.perf_counter() - started) * 1000)
        checked = []; answers = []
        client = VLMClient(grounding_engine=GroundingEngine(self.storage.parent/'crops'), timeout_seconds=45)
        verification_ms = 0

        def inspect(candidates):
            nonlocal verification_ms
            for _,source,page in candidates:
                if (source['docId'], page) in {(item['fileId'], item['page']) for item in checked}:
                    continue
                visual_page = self.evidence_page(source, page)
                pdf = self.storage/source['docId']/'source.pdf'
                page_started = time.perf_counter()
                with self.model_lock:
                    answer = client.answer_page_query(query, visual_page, source['docId'], page)
                verification_ms += round((time.perf_counter() - page_started) * 1000)
                if answer.status.value == 'direct' and answer.citation is None and pdf.exists():
                    with self.native_lock:
                        phrase = (f"{answer.numeric_value:g} {answer.unit}" if answer.numeric_value is not None and answer.unit else answer.answer or '')
                        box = client.grounding_engine.locate_text_span(pdf, page, phrase)
                        if box:
                            answer.citation = client.grounding_engine.crop_evidence(visual_page,box,source['docId'],page)
                answer = AbstentionGuard.verify_answer(answer)
                self.last['model'] = {'status': 'connected', 'checkedAt': time.time()}
                checked.append({'fileId':source['docId'],'filename':source['filename'],'page':page})
                if answer.status.value == 'direct':
                    if answer.citation is None:
                        warnings.append(f"{source['filename']} p.{page}: the model response had no usable source location.")
                        continue
                    answers.append({'answer':answer.answer, 'displayAnswer':answer.display_answer or answer.answer,
                        'fileId':source['docId'],'filename':source['filename'], 'page':page,
                        'box':answer.citation.box_2d.model_dump(), 'status':'model_grounded'})
                    return True
            return False

        # One lexical candidate is enough for a fast direct path. A negative
        # verification deliberately falls through to the full visual method.
        found = inspect(candidates[:1])
        semantic_retrieval_ms = 0
        if not found:
            semantic_started = time.perf_counter()
            semantic_candidates, semantic_warnings = self.retrieve(sources, query, include_semantic=True)
            semantic_retrieval_ms = round((time.perf_counter() - semantic_started) * 1000)
            warnings.extend(semantic_warnings)
            inspect(semantic_candidates)
        timings = {'fastRetrievalMs': fast_retrieval_ms, 'semanticRetrievalMs': semantic_retrieval_ms, 'verificationMs': verification_ms,
                   'totalMs': round((time.perf_counter() - started) * 1000)}
        print(json.dumps({'event': 'citecanvas.ask', 'sourceCount': len(sources), 'checkedPages': len(checked), 'timingsMs': timings}), flush=True)
        return {'answers':answers,'checkedPages':checked,'warnings':list(dict.fromkeys(warnings)),
                'message': 'Model answer — open the source to check it.' if answers else 'I could not establish an answer from the retrieved pages. Try a more specific question or another source.',
                'model':client.model_name, 'timings': timings}

    def extract(self, ids, fields):
        if not isinstance(fields,list) or not 1 <= len(fields) <= 4 or any(not isinstance(f,str) or not f.strip() or len(f)>120 for f in fields):
            raise ValueError('Enter 1–4 field names, one per line (up to 120 characters each).')
        sources = self.sources(ids)
        if len(sources)>4:raise ValueError('Extract from up to 4 PDFs per run.')
        rows=[]
        for source in sources:
            for field in fields:
                result=self.ask([source['docId']],f'What is the {field}? Return only the value as written on the page. If it is not stated, abstain.')
                answer=result['answers'][0] if result['answers'] else None
                rows.append({'filename':source['filename'],'field':field,'value':answer['answer'] if answer else '',
                    'status':'model_grounded' if answer else 'not_found','citation':answer,'review':'Not reviewed'})
        return {'rows':rows,'message':'Model-extracted values require source review.'}

    def compare(self, ids):
        sources=self.sources(ids)
        if len(sources)!=2 or sources[0]['docId']==sources[1]['docId']:raise ValueError('Select two different PDFs.')
        def lines(source):
            return [(line.strip(),int(page)) for page,text in sorted(source.get('pageText',{}).items(),key=lambda x:int(x[0])) for line in text.splitlines() if line.strip()]
        a,b=map(lines,sources)
        if not a or not b:raise ValueError('Text comparison needs readable native text in both PDFs. Scanned pages need OCR first.')
        matcher=difflib.SequenceMatcher(None,[x[0] for x in a],[x[0] for x in b],autojunk=False)
        changes=[]
        for kind,i,j,k,l in matcher.get_opcodes():
            if kind=='equal':continue
            changes.append({'kind':kind,'before':'\n'.join(x[0] for x in a[i:j]),'after':'\n'.join(x[0] for x in b[k:l]),
                'sourceA':{'fileId':sources[0]['docId'],'filename':sources[0]['filename'],'page':a[i][1]} if i<j else None,
                'sourceB':{'fileId':sources[1]['docId'],'filename':sources[1]['filename'],'page':b[k][1]} if k<l else None})
        return {'changes':changes[:200],'total':len(changes),'truncated':len(changes)>200,'method':'Exact text comparison; formatting and visual-only changes are not assessed.'}
