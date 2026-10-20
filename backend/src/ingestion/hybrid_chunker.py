"""
Structure-Aware Hybrid Chunker (Step 11).
Implements content-specific chunking policies, parent-child contextual links,
table-specific row-group splitting with repeated headers, independent visual routing,
and retrieval-time evidence expansion for grounded answering.

Content Policies:
- Narrative paragraphs: 350-500 body tokens, cap final searchable representation at 640 tokens.
- Oversized text: sentence-boundary splitting, source offsets, at most 1 preceding sentence overlap (~64 tokens).
- Lists and procedures: list-aware grouping, keep complete steps together.
- Small tables: whole-table retrieval chunk if within 768-token budget.
- Large tables: token-budgeted row groups capped at 768 tokens with repeated hierarchical headers and units.
- Wide tables: key-preserving column groups repeating row identifiers.
- Visual elements (stamps, signatures, equations, figures): preserved as independent regions, unpadded, context-linked.
- Representation separation: source_text, search_text, generated_context, local_identifiers, relations.
"""

import re
import uuid
from typing import Dict, List, Optional, Tuple

from backend.src.schemas.contracts import (
    BoundingBox,
    DocumentRegion,
    ExpandedEvidence,
    ExtractionMethod,
    FloatBoundingBox,
    QualityStatus,
    RegionType,
    StructuredDocument,
    StructuredTable,
    TableCell,
)
from backend.src.organization.contextual_indexer import ContextualIndexer


class HybridChunker:
    """
    Structure-aware chunker implementing element routing, token-budgeted row grouping,
    clean representation separation, and parent-child retrieval expansion.
    """

    # Content-specific token policies
    PROSE_TARGET_MIN = 350
    PROSE_TARGET_MAX = 500
    PROSE_SEARCH_CAP = 640
    SENTENCE_OVERLAP_CAP = 64
    TABLE_SEARCH_CAP = 768
    EVIDENCE_EXPANSION_BUDGET = 8000

    # Running furniture patterns to exclude from ordinary text chunks
    PAGE_FURNITURE_PATTERNS = [
        re.compile(r"^page\s+\d+(\s+of\s+\d+)?$", re.IGNORECASE),
        re.compile(r"^\d+\s*/\s*\d+$"),
        re.compile(r"^\d+$"),
        re.compile(r"^(confidential|draft|internal use only)$", re.IGNORECASE),
    ]

    # Known abbreviations that do not terminate sentences
    ABBREVIATIONS = {
        "e.g.", "i.e.", "fig.", "no.", "dr.", "mr.", "mrs.", "ms.",
        "approx.", "vol.", "p.", "pp.", "inc.", "ltd.", "vs.", "al."
    }

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """
        Estimates subword tokens accurately based on whitespace and punctuation tokens.
        Calibrated to match standard BGE-M3 / Llama tokenization (~1.3x words).
        """
        if not text:
            return 0
        words = text.split()
        return max(1, int(len(words) * 1.3))

    @classmethod
    def count_tokens(cls, text: str, tokenizer=None) -> int:
        """
        Counts tokens using a supplied tokenizer or falls back to calibrated estimate.
        Ensures the total serialized input (prefix + content + repeated headers) is measured.
        """
        if tokenizer is not None and callable(tokenizer):
            return len(tokenizer(text))
        return cls.estimate_tokens(text)

    @classmethod
    def is_page_furniture(cls, text: str) -> bool:
        """
        Detects running headers, footers, and page-counter artifacts.
        Excludes repetitive furniture from search chunks while preserving source provenance.
        """
        stripped = text.strip()
        if not stripped:
            return True
        for pat in cls.PAGE_FURNITURE_PATTERNS:
            if pat.match(stripped):
                return True
        return False

    @classmethod
    def split_into_sentences(cls, text: str) -> List[Tuple[str, int, int]]:
        """
        Splits text at sentence boundaries while recording character offsets (start, end).
        Respects common abbreviations and acronyms.
        """
        sentences: List[Tuple[str, int, int]] = []
        if not text:
            return sentences

        # Find potential sentence ends: . ! ? followed by whitespace
        candidates = list(re.finditer(r"([.!?]+)(\s+|$)", text))
        if not candidates:
            return [(text.strip(), 0, len(text))]

        start_idx = 0
        for match in candidates:
            punct = match.group(1)
            end_match = match.end()
            candidate_sentence = text[start_idx:match.start() + len(punct)].strip()
            
            # Check if this period is part of an abbreviation (e.g., 'e.g.', 'Fig.')
            words = candidate_sentence.split()
            last_word = words[-1].lower() if words else ""
            if last_word in cls.ABBREVIATIONS and match != candidates[-1]:
                # Don't split on abbreviations
                continue

            if candidate_sentence:
                sentences.append((candidate_sentence, start_idx, match.start() + len(punct)))
                start_idx = end_match

        # Any trailing text
        if start_idx < len(text):
            trailing = text[start_idx:].strip()
            if trailing:
                sentences.append((trailing, start_idx, len(text)))

        return sentences


    @classmethod
    def extract_local_identifiers(cls, text: str) -> List[str]:
        """
        Extracts locally scoped identifiers (lot numbers, ECNs, part numbers, units)
        from this specific chunk's content to avoid cross-chunk false matches.
        """
        lot_matches = re.findall(r"\b(?:lot|batch)\s*(?:no\.?|#)?\s*[:\-]?\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
        ecn_matches = re.findall(r"\bECN-[0-9]{4}-[0-9]{3,5}\b", text, re.IGNORECASE)
        part_matches = re.findall(r"\b(?:part|catalog|ref)\s*(?:no\.?|#)?\s*[:\-]?\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
        
        extracted = []
        for m in lot_matches + ecn_matches + part_matches:
            clean = m.strip()
            if clean and clean not in extracted and len(clean) < 30:
                extracted.append(clean)
        return extracted[:4]

    # -------------------------------------------------------------------------
    # 1. TABLE CHUNKING ALGORITHM
    # -------------------------------------------------------------------------
    @classmethod
    def chunk_table(
        cls,
        table: StructuredTable,
        max_rows_per_group: Optional[int] = None,
        token_budget: int = TABLE_SEARCH_CAP,
        doc_title: str = "Document",
        section_path: Optional[str] = None,
    ) -> List[DocumentRegion]:
        """
        Token-budgeted table row grouping with repeated hierarchical headers.
        Preserves original structured table and links continuation pages/footnotes.
        """
        chunks: List[DocumentRegion] = []
        if not table.rows:
            return chunks

        # Extract unit/period metadata if present
        table_unit = None
        for cell in table.cells:
            if cell.unit:
                table_unit = cell.unit
                break

        # Check if table fits entirely as a whole-table chunk
        full_md = table.markdown_representation
        total_tokens = cls.estimate_tokens(full_md)
        if max_rows_per_group is None and total_tokens <= token_budget:
            prefix = ContextualIndexer.create_contextual_prefix(
                doc_title=doc_title,
                section_path=section_path or table.caption,
                table_title=table.caption or table.table_id,
                unit=table_unit,
                include_provenance_tag=False,
            )
            search_text = prefix + full_md
            chunk = DocumentRegion(
                region_id=f"{table.table_id}_full",
                parent_section_id=table.caption,
                page_number=table.page_number,
                region_type=RegionType.TABLE,
                text=full_md,
                source_text=full_md,
                search_text=search_text,
                token_count=cls.estimate_tokens(search_text),
                box_2d=table.box_2d,
                extraction_method=ExtractionMethod.DOCLING_LAYOUT,
                quality_status=QualityStatus.VERIFIED,
                structured_table=table,
                local_identifiers=cls.extract_local_identifiers(full_md),
                relations=[table.table_id] + ([f"continues_p{table.continues_on_page}"] if table.continues_on_page else []),
            )
            return [chunk]

        # Build repeated header markdown
        header_md = ""
        header_tokens = 0
        if table.headers:
            header_md = "| " + " | ".join(table.headers) + " |\n| " + " | ".join(["---"] * len(table.headers)) + " |\n"
            header_tokens = cls.estimate_tokens(header_md)

        # Context prefix for table chunks
        prefix = ContextualIndexer.create_contextual_prefix(
            doc_title=doc_title,
            section_path=section_path or table.caption,
            table_title=table.caption or table.table_id,
            unit=table_unit,
            include_provenance_tag=False,
        )
        prefix_tokens = cls.estimate_tokens(prefix)
        effective_budget = max(20, token_budget - header_tokens - prefix_tokens)

        # Row grouping: accumulate complete rows until budget exceeded
        current_rows: List[List[str]] = []
        current_tokens = 0
        group_idx = 1
        start_row_idx = 0

        for r_idx, row in enumerate(table.rows):
            # Check if explicit row limit is forced (e.g. legacy test)
            if max_rows_per_group is not None and len(current_rows) >= max_rows_per_group:
                # Flush group
                chunk = cls._create_table_row_group_chunk(
                    table=table,
                    group_rows=current_rows,
                    header_md=header_md,
                    prefix=prefix,
                    group_idx=group_idx,
                    start_row=start_row_idx + 1,
                    end_row=r_idx,
                )
                chunks.append(chunk)
                group_idx += 1
                current_rows = []
                current_tokens = 0
                start_row_idx = r_idx

            row_md = "| " + " | ".join(row) + " |"
            row_tokens = cls.estimate_tokens(row_md)

            # Wide row handling: if single row exceeds budget, split columns while repeating key
            if row_tokens > effective_budget and len(row) > 3:
                if current_rows:
                    chunk = cls._create_table_row_group_chunk(
                        table=table,
                        group_rows=current_rows,
                        header_md=header_md,
                        prefix=prefix,
                        group_idx=group_idx,
                        start_row=start_row_idx + 1,
                        end_row=r_idx,
                    )
                    chunks.append(chunk)
                    group_idx += 1
                    current_rows = []
                    current_tokens = 0

                col_chunks = cls._split_wide_row(
                    table=table,
                    row=row,
                    prefix=prefix,
                    effective_budget=effective_budget,
                    group_idx=group_idx,
                    row_num=r_idx + 1,
                )
                chunks.extend(col_chunks)
                group_idx += len(col_chunks)
                start_row_idx = r_idx + 1
                continue

            if current_rows and (current_tokens + row_tokens > effective_budget):
                chunk = cls._create_table_row_group_chunk(
                    table=table,
                    group_rows=current_rows,
                    header_md=header_md,
                    prefix=prefix,
                    group_idx=group_idx,
                    start_row=start_row_idx + 1,
                    end_row=r_idx,
                )
                chunks.append(chunk)
                group_idx += 1
                current_rows = []
                current_tokens = 0
                start_row_idx = r_idx

            current_rows.append(row)
            current_tokens += row_tokens

        # Flush final rows
        if current_rows:
            chunk = cls._create_table_row_group_chunk(
                table=table,
                group_rows=current_rows,
                header_md=header_md,
                prefix=prefix,
                group_idx=group_idx,
                start_row=start_row_idx + 1,
                end_row=len(table.rows),
            )
            chunks.append(chunk)

        return chunks

    @classmethod
    def _create_table_row_group_chunk(
        cls,
        table: StructuredTable,
        group_rows: List[List[str]],
        header_md: str,
        prefix: str,
        group_idx: int,
        start_row: int,
        end_row: int,
    ) -> DocumentRegion:
        rows_md = "\n".join(["| " + " | ".join(r) + " |" for r in group_rows])
        core_text = header_md + rows_md
        search_text = prefix + core_text
        chunk_id = f"{table.table_id}_grp_{group_idx}"

        flags = ["repeated_table_headers", f"rows_{start_row}_to_{end_row}"]
        if table.continued_from_page:
            flags.append(f"continued_from_p{table.continued_from_page}")
        if table.continues_on_page:
            flags.append(f"continues_on_p{table.continues_on_page}")

        relations = [table.table_id]
        if table.caption:
            relations.append(table.caption)

        return DocumentRegion(
            region_id=chunk_id,
            parent_section_id=table.caption or table.table_id,
            page_number=table.page_number,
            region_type=RegionType.TABLE_ROW_GROUP,
            text=core_text,
            source_text=core_text,
            search_text=search_text,
            token_count=cls.estimate_tokens(search_text),
            box_2d=table.box_2d,
            extraction_method=ExtractionMethod.DOCLING_LAYOUT,
            quality_status=QualityStatus.VERIFIED,
            quality_flags=flags,
            local_identifiers=cls.extract_local_identifiers(core_text),
            relations=relations,
        )

    @classmethod
    def _split_wide_row(
        cls,
        table: StructuredTable,
        row: List[str],
        prefix: str,
        effective_budget: int,
        group_idx: int,
        row_num: int,
    ) -> List[DocumentRegion]:
        """
        Splits a very wide table row into column groups while repeating the primary row identifier.
        """
        chunks = []
        row_key = row[0] if row else "Row"
        headers = table.headers if table.headers else [f"Col{i}" for i in range(len(row))]
        header_key = headers[0] if headers else "Key"

        # Group columns 2-3 at a time with the key column
        col_step = max(2, len(row) // 3)
        subgroup_num = 1
        for c_start in range(1, len(row), col_step):
            c_end = min(len(row), c_start + col_step)
            sub_headers = [header_key] + headers[c_start:c_end]
            sub_row = [row_key] + row[c_start:c_end]

            sub_header_md = "| " + " | ".join(sub_headers) + " |\n| " + " | ".join(["---"] * len(sub_headers)) + " |\n"
            sub_row_md = "| " + " | ".join(sub_row) + " |"
            core_text = sub_header_md + sub_row_md
            search_text = prefix + core_text

            chunk_id = f"{table.table_id}_grp_{group_idx}_colgrp_{subgroup_num}"
            chunks.append(
                DocumentRegion(
                    region_id=chunk_id,
                    parent_section_id=table.caption or table.table_id,
                    page_number=table.page_number,
                    region_type=RegionType.TABLE_ROW_GROUP,
                    text=core_text,
                    source_text=core_text,
                    search_text=search_text,
                    token_count=cls.estimate_tokens(search_text),
                    box_2d=table.box_2d,
                    extraction_method=ExtractionMethod.DOCLING_LAYOUT,
                    quality_status=QualityStatus.VERIFIED,
                    quality_flags=["repeated_table_headers", f"row_{row_num}_column_group_{subgroup_num}"],
                    local_identifiers=cls.extract_local_identifiers(core_text),
                    relations=[table.table_id],
                )
            )
            subgroup_num += 1

        return chunks

    # -------------------------------------------------------------------------
    # 2. PROSE CHUNKING ALGORITHM
    # -------------------------------------------------------------------------
    @classmethod
    def chunk_prose_stream(
        cls,
        regions: List[DocumentRegion],
        doc_title: str = "Document",
        section_path: Optional[str] = None,
    ) -> List[DocumentRegion]:
        """
        Chunks narrative paragraphs and long passages respecting sentence boundaries,
        350-500 token target, 640 token final search cap, and controlled 1-sentence overlap.
        Excludes page furniture and prevents merging across section boundaries.
        """
        final_chunks: List[DocumentRegion] = []
        text_buffer: List[str] = []
        box_buffer: List[BoundingBox] = []
        buffer_tokens = 0
        first_page = 1
        last_sentence_overlap = ""

        prefix = ContextualIndexer.create_contextual_prefix(
            doc_title=doc_title,
            section_path=section_path,
            include_provenance_tag=False,
        )
        prefix_tokens = cls.estimate_tokens(prefix)
        body_budget = max(200, cls.PROSE_SEARCH_CAP - prefix_tokens)

        def flush_buffer(continuation: bool = False):
            nonlocal text_buffer, box_buffer, buffer_tokens, first_page, last_sentence_overlap
            if not text_buffer:
                return

            body_text = "\n\n".join(text_buffer)
            search_text = prefix + body_text
            chunk_tokens = cls.estimate_tokens(search_text)

            combined_box = None
            if box_buffer:
                ymin = min(b.ymin for b in box_buffer)
                xmin = min(b.xmin for b in box_buffer)
                ymax = max(b.ymax for b in box_buffer)
                xmax = max(b.xmax for b in box_buffer)
                combined_box = BoundingBox(ymin=ymin, xmin=xmin, ymax=ymax, xmax=xmax)

            chunk_id = f"p{first_page}_prose_{uuid.uuid4().hex[:6]}"
            flags = []
            if continuation:
                flags.append("continuation")

            final_chunks.append(
                DocumentRegion(
                    region_id=chunk_id,
                    parent_section_id=section_path,
                    page_number=first_page,
                    region_type=RegionType.PARAGRAPH,
                    text=body_text,
                    source_text=body_text,
                    search_text=search_text,
                    token_count=chunk_tokens,
                    box_2d=combined_box,
                    extraction_method=ExtractionMethod.DOCLING_LAYOUT,
                    quality_status=QualityStatus.VERIFIED,
                    quality_flags=flags,
                    local_identifiers=cls.extract_local_identifiers(body_text),
                    relations=[section_path] if section_path else [],
                )
            )

            # Keep at most one preceding sentence (~64 tokens) only when forced to split a continuous passage
            sentences = cls.split_into_sentences(body_text)
            if sentences:
                candidate_overlap = sentences[-1][0]
                if cls.estimate_tokens(candidate_overlap) <= cls.SENTENCE_OVERLAP_CAP:
                    last_sentence_overlap = candidate_overlap
                else:
                    last_sentence_overlap = ""
            else:
                last_sentence_overlap = ""

            text_buffer = []
            box_buffer = []
            buffer_tokens = 0

        for reg in regions:
            raw_text = reg.text.strip()
            if not raw_text or cls.is_page_furniture(raw_text):
                continue

            first_page = reg.page_number
            reg_tokens = cls.estimate_tokens(raw_text)

            # If oversized paragraph (> body_budget), split at sentence boundaries
            if reg_tokens > body_budget:
                flush_buffer()
                sentences = cls.split_into_sentences(raw_text)
                for sentence_text, start_off, end_off in sentences:
                    s_tokens = cls.estimate_tokens(sentence_text)

                    # If single sentence exceeds budget, token-aware fallback marked as continuation
                    if s_tokens > body_budget:
                        flush_buffer()
                        words = sentence_text.split()
                        w_step = max(20, int(body_budget / 1.5))
                        for w_start in range(0, len(words), w_step):
                            sub_text = " ".join(words[w_start : w_start + w_step])
                            text_buffer.append(sub_text)
                            if reg.box_2d:
                                box_buffer.append(reg.box_2d)
                            flush_buffer(continuation=(w_start > 0))
                        continue

                    # If adding sentence would exceed body budget, flush first
                    if buffer_tokens > 0 and (buffer_tokens + s_tokens > body_budget or buffer_tokens >= cls.PROSE_TARGET_MAX):
                        flush_buffer(continuation=True)
                        if last_sentence_overlap:
                            text_buffer.append(last_sentence_overlap)
                            buffer_tokens += cls.estimate_tokens(last_sentence_overlap)

                    text_buffer.append(sentence_text)
                    if reg.box_2d:
                        box_buffer.append(reg.box_2d)
                    buffer_tokens += s_tokens

                flush_buffer()
                last_sentence_overlap = ""
                continue

            # Standard paragraph merge check: flush if adding reg_tokens exceeds budget
            if buffer_tokens > 0 and (buffer_tokens + reg_tokens > body_budget or buffer_tokens >= cls.PROSE_TARGET_MAX):
                flush_buffer()
                last_sentence_overlap = ""  # No blanket overlap between naturally bounded paragraphs


            text_buffer.append(raw_text)
            if reg.box_2d:
                box_buffer.append(reg.box_2d)
            buffer_tokens += reg_tokens

        flush_buffer()
        return final_chunks

    # -------------------------------------------------------------------------
    # 3. MASTER ROUTING & CHUNKING ORCHESTRATION
    # -------------------------------------------------------------------------
    @classmethod
    def chunk_document_regions(
        cls,
        regions: List[DocumentRegion],
        tables: List[StructuredTable],
        doc_title: str = "Document",
    ) -> List[DocumentRegion]:
        """
        Routes elements into appropriate streams before applying chunking rules.
        Prevents merging across logical documents, unrelated sections, tables, and visual boundaries.
        """
        final_chunks: List[DocumentRegion] = []

        # 1. Process structured tables with token-budgeted row groups
        for tbl in tables:
            tbl_chunks = cls.chunk_table(tbl, doc_title=doc_title)
            final_chunks.extend(tbl_chunks)

        # 2. Route non-table regions: separate prose streams by section
        current_section = None
        prose_stream: List[DocumentRegion] = []

        def flush_prose_stream():
            nonlocal prose_stream
            if prose_stream:
                p_chunks = cls.chunk_prose_stream(
                    regions=prose_stream,
                    doc_title=doc_title,
                    section_path=current_section,
                )
                final_chunks.extend(p_chunks)
                prose_stream = []

        for reg in regions:
            # Table regions handled in tables stream
            if reg.region_type == RegionType.TABLE:
                continue

            # Visual elements routed independently: stamps, signatures, equations, figures
            if reg.region_type in (
                RegionType.STAMP,
                RegionType.SIGNATURE,
                RegionType.EQUATION,
                RegionType.FIGURE,
                RegionType.CHART,
            ):
                flush_prose_stream()
                # Create clean separate search_text for visual element without padding
                prefix = ContextualIndexer.create_contextual_prefix(
                    doc_title=doc_title,
                    section_path=reg.parent_section_id or current_section,
                    include_provenance_tag=False,
                )
                reg.search_text = prefix + reg.text
                reg.token_count = cls.estimate_tokens(reg.search_text)
                reg.local_identifiers = cls.extract_local_identifiers(reg.text)
                final_chunks.append(reg)
                continue

            # Heading regions reset section context and are preserved as navigational elements
            if reg.region_type == RegionType.HEADING:
                flush_prose_stream()
                current_section = reg.text
                final_chunks.append(reg)
                continue

            # Accumulate prose for current section
            prose_stream.append(reg)

        flush_prose_stream()
        return final_chunks

    # -------------------------------------------------------------------------
    # 4. RETRIEVAL-TIME CONTEXT EXPANSION (Parent-Child)
    # -------------------------------------------------------------------------
    @classmethod
    def expand_evidence(
        cls,
        retrieved_chunk: DocumentRegion,
        structured_doc: StructuredDocument,
        max_expansion_tokens: int = EVIDENCE_EXPANSION_BUDGET,
    ) -> ExpandedEvidence:
        """
        Expands a retrieved child chunk into complete grounded evidence for answering.
        - Paragraph -> parent section and adjacent paragraphs.
        - Table row group -> headers, units, full table, and linked footnotes.
        - Figure/Chart -> image crop, caption, and nearby explanation.
        - Stamp/Signature -> region image crop and surrounding verification block.
        - Equation -> definitions and mathematical context.
        """
        chunk_type = retrieved_chunk.region_type
        core_text = retrieved_chunk.source_text or retrieved_chunk.text
        expanded_parts: List[str] = [f"### Primary Retrieved Chunk ({chunk_type.value})\n{core_text}"]
        parent_sec = retrieved_chunk.parent_section_id
        linked_table = None
        linked_footnotes: List[str] = []
        linked_image = retrieved_chunk.source_crop_path

        # 1. Expand Table Row Groups
        if chunk_type in (RegionType.TABLE, RegionType.TABLE_ROW_GROUP):
            # Find parent table
            for tbl in structured_doc.tables:
                if tbl.table_id in retrieved_chunk.region_id or (tbl.caption and tbl.caption == parent_sec):
                    linked_table = tbl
                    break

            if linked_table:
                expanded_parts.append(f"### Full Structured Table Context ({linked_table.table_id})\n{linked_table.markdown_representation}")

            # Find linked footnotes
            for rel in structured_doc.relationships:
                if rel.target_id == retrieved_chunk.region_id and rel.relation_type == "footnote_for":
                    for r in structured_doc.regions:
                        if r.region_id == rel.source_id:
                            linked_footnotes.append(r.text)
                            expanded_parts.append(f"### Linked Footnote\n{r.text}")

        # 2. Expand Narrative Paragraphs to Parent Section
        elif chunk_type == RegionType.PARAGRAPH:
            section_chunks = [
                r.text for r in structured_doc.regions
                if r.parent_section_id == parent_sec and r.region_id != retrieved_chunk.region_id
            ]
            if section_chunks:
                context_block = "\n\n".join(section_chunks[:3])
                expanded_parts.append(f"### Surrounding Section Context ({parent_sec})\n{context_block}")

        # 3. Expand Visual Elements (Stamps, Signatures, Figures)
        elif chunk_type in (RegionType.STAMP, RegionType.SIGNATURE, RegionType.FIGURE, RegionType.CHART):
            same_page_regions = [
                r.text for r in structured_doc.regions
                if r.page_number == retrieved_chunk.page_number and r.region_id != retrieved_chunk.region_id
            ]
            if same_page_regions:
                expanded_parts.append(f"### Surrounding Page {retrieved_chunk.page_number} Context\n" + "\n".join(same_page_regions[:2]))

        expanded_text = "\n\n".join(expanded_parts)
        total_tokens = cls.estimate_tokens(expanded_text)
        is_truncated = False

        if total_tokens > max_expansion_tokens:
            words = expanded_text.split()
            budget_words = int(max_expansion_tokens / 1.3)
            expanded_text = " ".join(words[:budget_words]) + "\n\n... [Evidence Context Truncated at Budget]"
            total_tokens = max_expansion_tokens
            is_truncated = True

        return ExpandedEvidence(
            chunk_id=retrieved_chunk.region_id,
            region_type=chunk_type,
            page_number=retrieved_chunk.page_number,
            core_text=core_text,
            expanded_text=expanded_text,
            token_count=total_tokens,
            parent_section=parent_sec,
            linked_table=linked_table,
            linked_footnotes=linked_footnotes,
            linked_image_crop_path=linked_image,
            box_2d=retrieved_chunk.box_2d,
            relations=retrieved_chunk.relations,
            is_truncated=is_truncated,
        )


class LateChunker:
    """
    Optional late-chunking path: obtains contextualized token embeddings across
    a bounded document section/window and pools vectors for each chunk boundary.
    """

    @classmethod
    def pool_chunk_token_embeddings(
        cls,
        token_embeddings: List[List[float]],
        chunk_token_spans: List[Tuple[int, int]],
    ) -> List[List[float]]:
        """
        Mean-pools token vectors within each chunk's (start_token, end_token) boundary.
        """
        pooled_vectors: List[List[float]] = []
        for start_idx, end_idx in chunk_token_spans:
            span_vectors = token_embeddings[start_idx:end_idx]
            if not span_vectors:
                pooled_vectors.append([])
                continue
            dim = len(span_vectors[0])
            pooled = [sum(v[d] for v in span_vectors) / len(span_vectors) for d in range(dim)]
            pooled_vectors.append(pooled)
        return pooled_vectors
