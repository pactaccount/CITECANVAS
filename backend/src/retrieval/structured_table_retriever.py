"""
Structured Table & Cell Retrieval Engine.
Indexes tables with explicit structural coordinates:
- Row labels
- Column headers
- Cell values (numeric and text)
- Units and scaling factors
- Time periods / revisions
- Linked footnotes and bounding boxes

Supports:
1. Metric & Cell Retrieval: Locates precise cell values with complete row/column/unit context.
2. Exhaustive Enumeration & Aggregation: Deterministic execution for tasks like
   "list all", "sum", "average", "where value > X" that cannot be solved by top-k semantic search.
"""

import re
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field

from backend.src.schemas.contracts import BoundingBox


class TableCellRecord(BaseModel):
    """Atomic cell record with complete structural provenance."""
    cell_id: str
    table_id: str
    doc_id: str
    page_number: int
    row_idx: int
    col_idx: int
    row_label: str
    column_header: str
    raw_value: str
    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    period_or_revision: Optional[str] = None
    footnotes: List[str] = Field(default_factory=list)
    box_2d: Optional[BoundingBox] = None


class StructuredTable(BaseModel):
    """Complete structured table schema with relational integrity."""
    table_id: str
    doc_id: str
    page_number: int
    title: Optional[str] = None
    headers: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)  # list of {col_header: val}
    cells: List[TableCellRecord] = Field(default_factory=list)
    footnotes: List[str] = Field(default_factory=list)
    box_2d: Optional[BoundingBox] = None


class StructuredTableRetriever:
    """
    Retrieves complete tabular evidence and executes deterministic operations.
    """

    def __init__(self):
        self._tables: Dict[str, StructuredTable] = {}  # table_id -> StructuredTable
        self._cells: List[TableCellRecord] = []
        self._doc_tables: Dict[str, List[str]] = {}  # doc_id -> list of table_ids

    def index_table(self, table: StructuredTable):
        """Indexes a structured table and all its constituent cells."""
        self._tables[table.table_id] = table
        self._cells.extend(table.cells)

        if table.doc_id not in self._doc_tables:
            self._doc_tables[table.doc_id] = []
        if table.table_id not in self._doc_tables[table.doc_id]:
            self._doc_tables[table.doc_id].append(table.table_id)

    def retrieve_metric_cells(
        self,
        metric_name: str,
        doc_id: Optional[str] = None,
        revision: Optional[str] = None,
        unit: Optional[str] = None,
    ) -> List[TableCellRecord]:
        """
        Locates cells matching the target metric, row label, or column header.
        Filters by document ID, revision, or measurement unit.
        """
        matches = []
        target_norm = metric_name.lower().strip()

        for cell in self._cells:
            if doc_id and cell.doc_id != doc_id:
                continue
            if revision and cell.period_or_revision and revision.upper() not in cell.period_or_revision.upper():
                continue
            if unit and cell.unit and unit.lower() not in cell.unit.lower():
                continue

            # Match against row label, column header, or raw value
            is_row_match = target_norm in cell.row_label.lower()
            is_col_match = target_norm in cell.column_header.lower()
            is_val_match = target_norm in cell.raw_value.lower()

            if is_row_match or is_col_match or is_val_match:
                matches.append(cell)

        return matches

    def retrieve_complete_table_evidence(
        self,
        table_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves the complete structured evidence package for an answering model:
        table title, all headers, row values, units, footnotes, and page coordinates.
        """
        table = self._tables.get(table_id)
        if not table:
            return None

        return {
            "table_id": table.table_id,
            "doc_id": table.doc_id,
            "page_number": table.page_number,
            "title": table.title,
            "headers": table.headers,
            "rows": table.rows,
            "footnotes": table.footnotes,
            "box_2d": table.box_2d.model_dump() if table.box_2d else None,
            "cell_count": len(table.cells),
        }

    def execute_aggregation(
        self,
        table_id: str,
        column_name: str,
        operation: str = "sum",  # sum, avg, min, max, count
        filter_predicate: Optional[str] = None,  # e.g., "> 25.0"
    ) -> Dict[str, Any]:
        """
        Executes a deterministic calculation over structured table cells.
        Bypasses LLM hallucinations for mathematical / exhaustive tasks.
        """
        table = self._tables.get(table_id)
        if not table:
            return {"status": "error", "message": f"Table {table_id} not found"}

        # Extract target numeric values
        values: List[float] = []
        matching_cells: List[TableCellRecord] = []

        col_norm = column_name.lower().strip()

        for cell in table.cells:
            if col_norm in cell.column_header.lower() or col_norm in cell.row_label.lower():
                if cell.numeric_value is not None:
                    # Apply optional filter predicate
                    if filter_predicate:
                        op_m = re.match(r"([><=!]+)\s*([0-9]+(?:\.[0-9]+)?)", filter_predicate.strip())
                        if op_m:
                            sym, threshold = op_m.group(1), float(op_m.group(2))
                            if sym == ">" and not (cell.numeric_value > threshold):
                                continue
                            elif sym == ">=" and not (cell.numeric_value >= threshold):
                                continue
                            elif sym == "<" and not (cell.numeric_value < threshold):
                                continue
                            elif sym == "<=" and not (cell.numeric_value <= threshold):
                                continue
                            elif sym == "==" and not (cell.numeric_value == threshold):
                                continue

                    values.append(cell.numeric_value)
                    matching_cells.append(cell)

        if not values:
            return {
                "status": "empty",
                "operation": operation,
                "count": 0,
                "result": None,
                "message": "No numeric values matched criteria",
            }

        if operation == "sum":
            result = sum(values)
        elif operation == "avg":
            result = sum(values) / len(values)
        elif operation == "min":
            result = min(values)
        elif operation == "max":
            result = max(values)
        elif operation == "count":
            result = len(values)
        else:
            return {"status": "error", "message": f"Unsupported operation: {operation}"}

        return {
            "status": "success",
            "operation": operation,
            "count": len(values),
            "result": result,
            "supporting_cells": [c.cell_id for c in matching_cells],
            "units": list(set(c.unit for c in matching_cells if c.unit)),
            "footnotes": list(set(fn for c in matching_cells for fn in c.footnotes)),
        }
