"""
Parent-Child Organization & Cross-Element Linking Engine (Steps 4 & 5).
Builds explicit typed links connecting:
- Table continuations across page boundaries
- Captions to figures/tables
- Footnotes to tables/paragraphs
- In-text references to figures and equations
- Parent-child containment links
"""

import re
from typing import List, Optional
from backend.src.schemas.contracts import (
    ContentRelationship,
    ContentRelationType,
    DocumentRegion,
    RegionType,
    StructuredTable,
)


class CrossElementLinker:
    """
    Identifies and persists cross-page and cross-element structural relationships.
    """

    FIG_REF_PATTERN = re.compile(r'\b(?:Figure|Fig\.?|Chart|Diagram)\s+(\d+[A-Za-z]?)', re.IGNORECASE)
    EQ_REF_PATTERN = re.compile(r'\b(?:Equation|Eq\.?)\s*\(?(\d+)\)?', re.IGNORECASE)
    FOOTNOTE_MARKER = re.compile(r'^[\*†‡§\d]\s+(.*)')

    @classmethod
    def link_table_continuations(
        cls,
        tables: List[StructuredTable],
    ) -> List[ContentRelationship]:
        """
        Detects tables spanning across consecutive page breaks.
        Links likely continuations using matching headers, column counts, and page adjacency.
        """
        relationships: List[ContentRelationship] = []
        if len(tables) < 2:
            return relationships

        sorted_tables = sorted(tables, key=lambda t: (t.page_number, t.table_id))

        for i in range(len(sorted_tables) - 1):
            t_curr = sorted_tables[i]
            t_next = sorted_tables[i + 1]

            # Check for adjacent pages
            if t_next.page_number == t_curr.page_number + 1:
                # 1. Matching column count
                col_match = len(t_curr.headers) == len(t_next.headers) and len(t_curr.headers) > 0
                # 2. Or identical headers
                header_match = t_curr.headers == t_next.headers if col_match else False

                if header_match or (col_match and len(t_curr.rows) > 0 and len(t_next.rows) > 0):
                    t_curr.continues_on_page = t_next.page_number
                    t_next.continued_from_page = t_curr.page_number

                    relationships.append(
                        ContentRelationship(
                            source_id=t_curr.table_id,
                            target_id=t_next.table_id,
                            relation_type=ContentRelationType.TABLE_CONTINUATION,
                            confidence=0.90 if header_match else 0.75,
                            description=f"Table continuing from Page {t_curr.page_number} to Page {t_next.page_number}",
                        )
                    )

        return relationships

    @classmethod
    def link_captions_and_footnotes(
        cls,
        regions: List[DocumentRegion],
    ) -> List[ContentRelationship]:
        """
        Connects captions to figures/tables and footnotes to tables on the same page.
        """
        relationships: List[ContentRelationship] = []
        page_regions = {}
        for r in regions:
            page_regions.setdefault(r.page_number, []).append(r)

        for page_num, r_list in page_regions.items():
            tables = [r for r in r_list if r.region_type in (RegionType.TABLE, RegionType.TABLE_ROW_GROUP)]
            figures = [r for r in r_list if r.region_type in (RegionType.FIGURE, RegionType.CHART)]
            paragraphs = [r for r in r_list if r.region_type == RegionType.PARAGRAPH]

            for p in paragraphs:
                # 1. Check for footnote
                if cls.FOOTNOTE_MARKER.match(p.text) or "note:" in p.text.lower() or "* " in p.text:
                    p.region_type = RegionType.FOOTNOTE
                    # Link to the nearest table on the same page
                    if tables:
                        relationships.append(
                            ContentRelationship(
                                source_id=p.region_id,
                                target_id=tables[-1].region_id,
                                relation_type=ContentRelationType.FOOTNOTE_FOR,
                                confidence=0.85,
                                description=f"Footnote on Page {page_num} modifying table {tables[-1].region_id}",
                            )
                        )

                # 2. Check for figure references in narrative
                fig_match = cls.FIG_REF_PATTERN.search(p.text)
                if fig_match and figures:
                    relationships.append(
                        ContentRelationship(
                            source_id=p.region_id,
                            target_id=figures[0].region_id,
                            relation_type=ContentRelationType.REFERENCES_FIGURE,
                            confidence=0.80,
                            description=f"Paragraph on Page {page_num} references {fig_match.group(0)}",
                        )
                    )

        return relationships
