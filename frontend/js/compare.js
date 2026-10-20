/* ==========================================================================
   EVID COMPARE DOCUMENTS & REVISIONS CONTROLLER
   - Strict sample mode labeling
   - Unsupported pairs show explicit unavailability (never wrong results)
   - Synchronizes headers, values, scope, and source links
   - Results marked stale immediately when selections change; disables stale exports
   - Labels different products Document A/Document B; Earlier/Later only for chronology
   - "Changes described in revision history" banner for packaging spec
   - Safe DOM rendering via textContent / DOM APIs (no innerHTML interpolation)
   ========================================================================== */

class CompareController {
  constructor() {
    // Sample workflows remain inactive in a real, empty workspace.
    if (!state.project.isSampleProject) return;
    this.tableBody = document.getElementById("compareTableBody");
    this.selectDocA = document.getElementById("compareDocASelect");
    this.selectDocB = document.getElementById("compareDocBSelect");
    this.selectScope = document.getElementById("compareModeSelect");
    this.btnRun = document.getElementById("btnRunCompare");
    this.thDocA = document.getElementById("compareThDocA");
    this.thDocB = document.getElementById("compareThDocB");
    this.labelDocA = document.getElementById("compareDocALabel");
    this.labelDocB = document.getElementById("compareDocBLabel");
    this.staleNotice = document.getElementById("compareStaleNotice");
    this.sampleBanner = document.getElementById("compareSampleBanner");
    this.btnExport = document.getElementById("btnExportCompare");

    this.currentRenderedKey = null;
    this.isStale = false;
    this.activeRunId = 0;

    this.initEvents();
    this.render(); // Initial load
  }

  initEvents() {
    this.btnRun.addEventListener("click", () => {
      this.activeRunId++;
      this.render();
    });

    const onSelectionChange = () => {
      this.markStale();
      this.updateSelectorLabels();
    };

    if (this.selectDocA) this.selectDocA.addEventListener("change", onSelectionChange);
    if (this.selectDocB) this.selectDocB.addEventListener("change", onSelectionChange);
    if (this.selectScope) this.selectScope.addEventListener("change", onSelectionChange);

    if (this.btnExport) {
      this.btnExport.addEventListener("click", () => this.exportCsv());
    }
  }

  getDatasetKey() {
    const a = this.selectDocA ? this.selectDocA.value : "";
    const b = this.selectDocB ? this.selectDocB.value : "";
    if (a === "packaging_revB" && b === "packaging_revC") return "packaging_revB_vs_revC";
    if (a === "low_flow" && b === "high_flow") return "low_flow_vs_high_flow";
    return null;
  }

  updateSelectorLabels() {
    const key = this.getDatasetKey();
    if (key === "packaging_revB_vs_revC") {
      if (this.labelDocA) this.labelDocA.textContent = "Earlier Document (Baseline)";
      if (this.labelDocB) this.labelDocB.textContent = "Later Document (Target)";
    } else {
      // Different products or other pairs
      if (this.labelDocA) this.labelDocA.textContent = "Document A";
      if (this.labelDocB) this.labelDocB.textContent = "Document B";
    }
  }

  markStale() {
    this.isStale = true;
    if (this.staleNotice) {
      this.staleNotice.style.display = "flex";
      this.staleNotice.textContent = "Selections have changed. Results below are stale — click Compare to update.";
    }
    if (this.btnExport) {
      this.btnExport.disabled = true;
      this.btnExport.title = "Selections have changed. Re-run comparison to export.";
    }
  }

  clearStale() {
    this.isStale = false;
    if (this.staleNotice) {
      this.staleNotice.style.display = "none";
      this.staleNotice.textContent = "";
    }
    if (this.btnExport) {
      this.btnExport.disabled = false;
      this.btnExport.title = "Export current comparison as CSV";
    }
  }

  render() {
    const runId = this.activeRunId;
    this.clearStale();
    this.updateSelectorLabels();

    const key = this.getDatasetKey();
    this.currentRenderedKey = key;
    this.tableBody.replaceChildren();

    // Handle unsupported combination
    if (!key || !PHARMA_SAMPLE_PROJECT.comparisonDatasets || !PHARMA_SAMPLE_PROJECT.comparisonDatasets[key]) {
      if (this.thDocA) this.thDocA.textContent = "Document A";
      if (this.thDocB) this.thDocB.textContent = "Document B";
      if (this.sampleBanner) this.sampleBanner.style.display = "none";
      if (this.btnExport) this.btnExport.disabled = true;

      const emptyRow = document.createElement("tr");
      const emptyCell = document.createElement("td");
      emptyCell.colSpan = 4;
      emptyCell.style.textAlign = "center";
      emptyCell.style.padding = "48px 24px";
      emptyCell.style.color = "var(--color-text-secondary)";

      const emptyTitle = document.createElement("div");
      emptyTitle.style.fontWeight = "600";
      emptyTitle.style.color = "var(--color-text-primary)";
      emptyTitle.style.marginBottom = "8px";
      emptyTitle.textContent = "No pre-computed comparison available for this combination.";

      const emptyDesc = document.createElement("div");
      emptyDesc.style.fontSize = "13px";
      emptyDesc.style.maxWidth = "520px";
      emptyDesc.style.margin = "0 auto";
      emptyDesc.textContent =
        "CiteCanvas displays only verified evidence-linked differences. Supported sample combinations are: Packaging Spec Rev B vs Rev C, or Low Flow Kit vs High Flow Kit.";

      emptyCell.appendChild(emptyTitle);
      emptyCell.appendChild(emptyDesc);
      emptyRow.appendChild(emptyCell);
      this.tableBody.appendChild(emptyRow);
      return;
    }

    const dataset = PHARMA_SAMPLE_PROJECT.comparisonDatasets[key];

    // Synchronize headers
    if (key === "packaging_revB_vs_revC") {
      if (this.thDocA) this.thDocA.textContent = "Earlier Document (Rev B)";
      if (this.thDocB) this.thDocB.textContent = "Later Document (Rev C)";
      if (this.sampleBanner) {
        this.sampleBanner.style.display = "flex";
        this.sampleBanner.replaceChildren();

        const badge = document.createElement("span");
        badge.className = "badge badge-warning";
        badge.textContent = "Sample Fixture";

        const text = document.createElement("span");
        text.style.fontSize = "13px";
        text.style.color = "var(--color-warning-text)";
        text.textContent =
          "Changes described in revision history. The current Revision C specification (DWG-29477427-PKG-R3, pp. 4–5) and its revision-history table are not independent original Revision B/C files. Do not infer historical values or unchanged properties from the current specification alone.";

        this.sampleBanner.appendChild(badge);
        this.sampleBanner.appendChild(text);
      }
    } else {
      // low_flow_vs_high_flow: Different products
      if (this.thDocA) this.thDocA.textContent = "Document A: " + dataset.docALabel;
      if (this.thDocB) this.thDocB.textContent = "Document B: " + dataset.docBLabel;
      if (this.sampleBanner) {
        this.sampleBanner.style.display = "flex";
        this.sampleBanner.replaceChildren();

        const badge = document.createElement("span");
        badge.className = "badge badge-info";
        badge.textContent = "Sample Mode · Different Products";

        const text = document.createElement("span");
        text.style.fontSize = "13px";
        text.style.color = "var(--color-info-text)";
        text.textContent =
          "Comparing two distinct products (Low Flow Kit Lot 18356721 vs High Flow Kit Lot 15102934). Items are labeled Document A / Document B because these are separate product lines, not sequential revisions.";

        this.sampleBanner.appendChild(badge);
        this.sampleBanner.appendChild(text);
      }
    }

    // Check race condition (ignore responses belonging to older selections)
    if (runId !== this.activeRunId) return;

    dataset.items.forEach((item) => {
      const tr = document.createElement("tr");

      // Column 1: Item / Requirement (safe textContent)
      const tdItem = document.createElement("td");
      tdItem.style.fontWeight = "600";
      tdItem.style.color = "var(--color-text-primary)";
      tdItem.style.width = "220px";
      tdItem.textContent = item.item;
      tr.appendChild(tdItem);

      // Column 2: Document A Value
      const tdDocA = document.createElement("td");
      const blockA = document.createElement("div");
      blockA.className = "diff-content-block";

      const valA = document.createElement("span");
      valA.className = "diff-value-text";
      valA.textContent = item.earlierVal;
      blockA.appendChild(valA);

      const srcA = document.createElement("span");
      srcA.style.fontSize = "11px";
      srcA.style.color = "var(--color-text-muted)";
      srcA.textContent = `Source: Page ${item.pageA}`;
      blockA.appendChild(srcA);

      const btnA = document.createElement("button");
      btnA.className = "btn btn-subtle btn-sm";
      btnA.style.alignSelf = "flex-start";
      btnA.style.padding = "0";
      btnA.style.color = "var(--color-primary)";
      btnA.style.fontSize = "12px";
      btnA.textContent = `Inspect Page ${item.pageA} →`;
      btnA.addEventListener("click", () => {
        state.openEvidence(item.pageA, null, `${dataset.docALabel} (Page ${item.pageA})`, btnA);
      });
      blockA.appendChild(btnA);
      tdDocA.appendChild(blockA);
      tr.appendChild(tdDocA);

      // Column 3: Document B Value
      const tdDocB = document.createElement("td");
      const blockB = document.createElement("div");
      blockB.className = "diff-content-block";

      const valB = document.createElement("span");
      valB.className = "diff-value-text";
      valB.textContent = item.laterVal;
      blockB.appendChild(valB);

      const srcB = document.createElement("span");
      srcB.style.fontSize = "11px";
      srcB.style.color = "var(--color-text-muted)";
      srcB.textContent = `Source: Page ${item.pageB}`;
      blockB.appendChild(srcB);

      const btnB = document.createElement("button");
      btnB.className = "btn btn-subtle btn-sm";
      btnB.style.alignSelf = "flex-start";
      btnB.style.padding = "0";
      btnB.style.color = "var(--color-primary)";
      btnB.style.fontSize = "12px";
      btnB.textContent = `Inspect Page ${item.pageB} →`;
      btnB.addEventListener("click", () => {
        state.openEvidence(item.pageB, null, `${dataset.docBLabel} (Page ${item.pageB})`, btnB);
      });
      blockB.appendChild(btnB);
      tdDocB.appendChild(blockB);
      tr.appendChild(tdDocB);

      // Column 4: Finding & Technical Analysis
      const tdAnalysis = document.createElement("td");
      const blockAnalysis = document.createElement("div");
      blockAnalysis.style.display = "flex";
      blockAnalysis.style.flexDirection = "column";
      blockAnalysis.style.gap = "6px";

      const pill = document.createElement("span");
      pill.className = `finding-pill ${item.findingClass || "finding-review"}`;
      pill.textContent = item.finding;
      blockAnalysis.appendChild(pill);

      const note = document.createElement("span");
      note.style.fontSize = "12px";
      note.style.color = "var(--color-text-secondary)";
      note.style.lineHeight = "1.45";
      note.textContent = item.note;
      blockAnalysis.appendChild(note);

      tdAnalysis.appendChild(blockAnalysis);
      tr.appendChild(tdAnalysis);

      this.tableBody.appendChild(tr);
    });
  }

  // Escape string for CSV with spreadsheet-formula protection
  sanitizeCsvCell(str) {
    if (str == null) return '""';
    let s = String(str);
    // Spreadsheet-formula protection: prepend single quote if starting with =, +, -, @, or tab
    if (/^[=+\-@\t\r]/.test(s)) {
      s = "'" + s;
    }
    // Escape internal quotes
    return `"${s.replace(/"/g, '""')}"`;
  }

  exportCsv() {
    if (this.isStale || !this.currentRenderedKey) return;
    const dataset = PHARMA_SAMPLE_PROJECT.comparisonDatasets[this.currentRenderedKey];
    if (!dataset) return;

    const headers = [
      "Item / Requirement",
      dataset.docALabel,
      dataset.docBLabel,
      "Finding",
      "Source Page A",
      "Source Page B",
      "Technical Analysis / Notes"
    ];

    let csvContent = headers.map(h => this.sanitizeCsvCell(h)).join(",") + "\n";

    dataset.items.forEach(item => {
      const row = [
        item.item,
        item.earlierVal,
        item.laterVal,
        item.finding,
        `Page ${item.pageA}`,
        `Page ${item.pageB}`,
        item.note
      ];
      csvContent += row.map(cell => this.sanitizeCsvCell(cell)).join(",") + "\n";
    });

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `evid_comparison_${this.currentRenderedKey}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }
}
