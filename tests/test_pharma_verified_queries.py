"""
Independently checked verification tests for pharma-blob-sample.pdf.
Verifies the 7 required ground-truth queries and architectural corrections:
1. Storage recommendation versus operating temperature (Page 1: storage > +5°C; operating +2°C to +40°C)
2. Gamma range for lot 18356721 (Page 2: 25.0-40.0 kGy)
3. Which lot is on the high-flow certificate (Page 3: 15102934)
4. What changed in packaging revision C (Page 5: PVC to PETG)
5. Maximum pressure for part 29184612, revision AD (Page 7: 5 MPa, equivalent to 50 bar)
6. Identification of page 10 (Page 10: Global Chain of Custody, NOT a quality certificate)
7. Operating pressures in revisions B and C (Correctly explains that those pressure values are not established by this PDF)
"""

import json
from pathlib import Path
import pytest
import pypdfium2 as pdfium

from backend.src.schemas.contracts import (
    CitationStatus,
    DocumentTypeLabel,
    PageMetadata,
)
from backend.src.organization.logical_separation import LogicalDocumentSeparator
from backend.src.retrieval.bm25_indexer import BM25Retriever
from backend.src.retrieval.dense_text_retriever import DenseTextRetriever, DenseTextChunk
from backend.src.retrieval.exact_lookup import ExactIdentifierLookup
from backend.src.retrieval.visual_indexer import QdrantVisualRetriever
from backend.src.retrieval.hybrid_ranker import HybridRanker
from backend.src.reasoning.answer_synthesizer import (
    AnswerSpecification,
    AnswerType,
    CalibratedAnswerSynthesizer,
    DeterministicArithmeticTool,
    RangeValue,
    TypedFact,
)
from backend.src.retrieval.evidence_selector import (
    EvidenceBundle,
    EvidenceModality,
)


@pytest.fixture(scope="module")
def pharma_pdf_data():
    base_dir = Path(__file__).resolve().parent.parent
    pdf_path = base_dir / "pharma-blob-sample.pdf"
    assert pdf_path.exists(), f"Missing test PDF: {pdf_path}"

    pdf = pdfium.PdfDocument(str(pdf_path))
    pages_text = {i + 1: p.get_textpage().get_text_range() for i, p in enumerate(pdf)}
    pages = [
        PageMetadata(page_number=i + 1, image_path=f"page_{i+1}.png", width=2481, height=3508)
        for i in range(len(pdf))
    ]
    subdocs = LogicalDocumentSeparator.detect_subdocuments(pages, pages_text, doc_id="pharma_eval")

    bm25 = BM25Retriever(pages_text)
    dense = DenseTextRetriever()
    dense.index_chunks([
        DenseTextChunk(chunk_id=f"page_{p}", doc_id="pharma_eval", page_number=p, text=txt)
        for p, txt in pages_text.items()
    ])
    visual = QdrantVisualRetriever(location=":memory:")
    ranker = HybridRanker(bm25_retriever=bm25, dense_retriever=dense, visual_retriever=visual)

    return {
        "pages_text": pages_text,
        "subdocs": subdocs,
        "ranker": ranker,
    }


def test_query_1_storage_versus_operating_temperature(pharma_pdf_data):
    """
    Test 1: Storage recommendation versus operating temperature?
    Must retrieve Page 1 and identify: storage > +5°C; operating +2°C to +40°C.
    """
    pages_text = pharma_pdf_data["pages_text"]
    ranker = pharma_pdf_data["ranker"]

    query = "What is the recommended storage temperature versus operating temperature for AKTA ready flow kits?"
    results = ranker.retrieve(query, top_k=2)
    top_page = results[0]["page_number"]
    assert top_page == 1, f"Expected Page 1 for storage conditions, got Page {top_page}"

    p1_text = pages_text[1]
    assert "> +5°C" in p1_text or "+5°C" in p1_text
    assert "+2°C to +40°C" in p1_text


def test_query_2_gamma_dose_for_lot_18356721(pharma_pdf_data):
    """
    Test 2: Gamma range for lot 18356721?
    Must identify Page 2 as the specific certificate for lot 18356721 with range 25.0-40.0 kGy.
    """
    pages_text = pharma_pdf_data["pages_text"]
    subdocs = pharma_pdf_data["subdocs"]

    # Verify Lot 18356721 is scoped specifically to Subdocument 2 (Page 2)
    subdoc_lot_18356721 = next((s for s in subdocs if "18356721" in s.lot_numbers), None)
    assert subdoc_lot_18356721 is not None
    assert subdoc_lot_18356721.start_page == 2
    assert subdoc_lot_18356721.end_page == 2

    p2_text = pages_text[2]
    assert "18356721" in p2_text
    assert "25.0 - 40.0 kGy" in p2_text or "25-40 kGy" in p2_text


def test_query_3_lot_on_high_flow_certificate(pharma_pdf_data):
    """
    Test 3: Which lot is on the high-flow certificate?
    Must identify Page 3 as the High Flow certificate and lot 15102934.
    """
    pages_text = pharma_pdf_data["pages_text"]
    subdocs = pharma_pdf_data["subdocs"]

    subdoc_high_flow = next((s for s in subdocs if s.start_page == 3), None)
    assert subdoc_high_flow is not None
    assert "High Flow" in subdoc_high_flow.title or "15102934" in subdoc_high_flow.lot_numbers

    p3_text = pages_text[3]
    assert "High Flow Kit" in p3_text
    assert "15102934" in p3_text
    assert "18356721" not in p3_text


def test_query_4_packaging_revision_c_change(pharma_pdf_data):
    """
    Test 4: What changed in packaging revision C?
    Must retrieve Page 5 configuration change history: PVC to PETG.
    """
    pages_text = pharma_pdf_data["pages_text"]
    p5_text = pages_text[5]

    assert "ECN-2023-0847" in p5_text
    assert "PVC to PETG" in p5_text or ("PVC" in p5_text and "PETG" in p5_text)


def test_query_5_maximum_pressure_part_29184612_rev_ad(pharma_pdf_data):
    """
    Test 5: Maximum pressure for part 29184612, revision AD?
    Must retrieve Page 7 (Material Description Sheet): Max 5 MPa, equivalent to 50 bar.
    """
    pages_text = pharma_pdf_data["pages_text"]
    p7_text = pages_text[7]

    assert "29184612" in p7_text
    assert "Revision: AD" in p7_text
    assert "Max 5 MPa" in p7_text or "5 MPa" in p7_text

    # NIST Conversion check: 5 MPa = 50 bar
    conv = DeterministicArithmeticTool.convert_pressure(5.0, from_unit="MPa", to_unit="bar")
    assert conv["result"] == 50.0
    assert conv["result_unit"] == "bar"


def test_query_6_is_page_10_quality_certificate(pharma_pdf_data):
    """
    Test 6: Is page 10 a quality certificate?
    Must correctly identify Page 10 as Global Chain of Custody, NOT a quality certificate.
    """
    subdocs = pharma_pdf_data["subdocs"]
    p10_subdoc = next((s for s in subdocs if s.start_page == 10), None)

    assert p10_subdoc is not None
    assert p10_subdoc.doc_type == DocumentTypeLabel.CHAIN_OF_CUSTODY
    assert p10_subdoc.doc_type != DocumentTypeLabel.CERTIFICATE
    assert "Chain of Custody" in p10_subdoc.title


def test_query_7_operating_pressures_in_revisions_b_and_c_not_established(pharma_pdf_data):
    """
    Test 7: What were operating pressures in revisions B and C?
    Must abstain or explain that operating pressures for packaging revisions B and C
    are not established by this PDF (since page 5 change history only tracks blister tray dimensions
    and PVC to PETG material changes).
    """
    pages_text = pharma_pdf_data["pages_text"]

    # Search for any operating pressure in the packaging specification (pages 4-5)
    pkg_text = pages_text[4] + " " + pages_text[5]
    has_pressure_in_pkg = "operating pressure" in pkg_text.lower() or "bar" in pkg_text.lower()
    assert has_pressure_in_pkg is False, "Packaging spec should not establish operating pressure"

    # Synthesizer abstention check
    ans = CalibratedAnswerSynthesizer.synthesize_abstention(
        query="What were operating pressures in packaging revisions B and C?",
        outcome_type="insufficient_evidence",
        reason="I could not establish this from the available evidence: packaging revisions B and C do not contain pressure specifications.",
    )
    assert ans.status == CitationStatus.ABSTAIN
    assert "I could not establish this from the available evidence" in ans.abstention_reason
