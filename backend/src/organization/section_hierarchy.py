"""
Section Hierarchy Reconstruction Engine (Step 3).
Combines PDF bookmarks, detected headings, numbering, typography, and reading order
to build navigable section trees with heading paths (e.g., '1.0 Overview > 1.2 Specs').
"""

import re
import uuid
from typing import Dict, List, Optional
from backend.src.schemas.contracts import (
    DocumentRegion,
    LogicalDocument,
    LogicalSection,
    RegionType,
)


class SectionHierarchyBuilder:
    """
    Reconstructs section trees and builds heading paths connecting logical sections to content elements.
    """

    NUMBERED_HEADING_PATTERN = re.compile(r'^(\d+(?:\.\d+)*)\s+(.*)')
    ITEM_HEADING_PATTERN = re.compile(r'^(ITEM\s+\d+[A-Z]?\.?)\s+(.*)', re.IGNORECASE)

    @classmethod
    def determine_heading_level(cls, heading_text: str) -> int:
        """Determines heading depth level based on numbering pattern or length."""
        m_num = cls.NUMBERED_HEADING_PATTERN.match(heading_text.strip())
        if m_num:
            parts = m_num.group(1).split('.')
            if len(parts) == 2 and parts[1] == '0':
                return 1
            return len(parts)

        m_item = cls.ITEM_HEADING_PATTERN.match(heading_text.strip())
        if m_item:
            return 1

        if len(heading_text) < 40 and heading_text.isupper():
            return 1
        return 2

    @classmethod
    def build_hierarchy(
        cls,
        regions: List[DocumentRegion],
        logical_docs: List[LogicalDocument],
    ) -> List[LogicalSection]:
        """
        Reconstructs section trees across logical documents, attaching element IDs to sections.
        """
        sections: List[LogicalSection] = []
        current_section: Optional[LogicalSection] = None
        heading_stack: List[Tuple[int, str]] = []  # (level, title)

        # Map page numbers to logical document id
        def get_subdoc_id(page_num: int) -> str:
            for ldoc in logical_docs:
                if ldoc.start_page <= page_num <= ldoc.end_page:
                    return ldoc.subdoc_id
            return logical_docs[0].subdoc_id if logical_docs else "doc_main"

        for reg in regions:
            subdoc_id = get_subdoc_id(reg.page_number)

            if reg.region_type == RegionType.HEADING:
                level = cls.determine_heading_level(reg.text)
                title = reg.text.strip()

                # Adjust heading stack to reflect hierarchy
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, title))

                heading_path = " > ".join([h[1] for h in heading_stack])
                parent_id = None
                if len(heading_stack) > 1:
                    parent_id = f"sec_{hash(heading_stack[-2][1]) % 100000}"

                sec_id = f"sec_{hash(title) % 100000}_{uuid.uuid4().hex[:4]}"
                current_section = LogicalSection(
                    section_id=sec_id,
                    logical_doc_id=subdoc_id,
                    title=title,
                    heading_level=level,
                    heading_path=heading_path,
                    parent_section_id=parent_id,
                    element_ids=[reg.region_id],
                )
                sections.append(current_section)
                reg.parent_section_id = sec_id
            else:
                if current_section:
                    current_section.element_ids.append(reg.region_id)
                    reg.parent_section_id = current_section.section_id

        return sections
