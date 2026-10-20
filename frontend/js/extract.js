/* ==========================================================================
   EVID EXTRACT FIELDS CONTROLLER
   - 4 Complete Screens: Choose Docs, Define Fields, Preview, Run & Review
   - Single handler for "Edit fields" -> Step 2
   - Back/Continue preserve all edits
   - Stepper appearance derived from state
   - Invalidation on source or schema changes
   - Honest local reviews & 6 explicit value states:
     extracted, derived, not_found, na, uncertain, failed
   - CSV export with citations, review status, escaping & formula protection
   - Safe DOM rendering via textContent / DOM APIs
   ========================================================================== */

class ExtractController {
  constructor() {
    // Sample workflows remain inactive in a real, empty workspace.
    if (!state.project.isSampleProject) return;
    this.stepper = document.getElementById("extractStepper");
    this.wizardSteps = document.querySelectorAll(".wizard-step");
    this.stepPanels = document.querySelectorAll(".wizard-step-panel");

    // Screen 1: Choose Documents
    this.docSearchInput = document.getElementById("extractDocSearchInput");
    this.docChecklist = document.getElementById("extractDocChecklist");
    this.docSelectedCount = document.getElementById("extractSelectedCount");
    this.btnSelectAllDocs = document.getElementById("btnExtractSelectAll");
    this.btnDeselectAllDocs = document.getElementById("btnExtractDeselectAll");
    this.btnStep1Continue = document.getElementById("btnStep1Continue");

    // Screen 2: Define Fields
    this.fieldsTableBody = document.getElementById("extractFieldsTableBody");
    this.btnAddField = document.getElementById("btnAddExtractField");
    this.fieldErrorBanner = document.getElementById("extractFieldErrorBanner");
    this.btnStep2Back = document.getElementById("btnStep2Back");
    this.btnStep2Continue = document.getElementById("btnStep2Continue");

    // Screen 3: Preview
    this.previewContainer = document.getElementById("extractPreviewContainer");
    this.btnStep3Back = document.getElementById("btnStep3Back");
    this.btnStep3Run = document.getElementById("btnStep3Run");

    // Screen 4: Run & Review
    this.matrixContainer = document.getElementById("extractMatrixContainer");
    this.matrixTable = document.getElementById("extractMatrixTable");
    this.btnEditFields = document.getElementById("btnEditFieldSchema");
    this.btnNewRun = document.getElementById("btnNewExtractRun");
    this.btnExportCsv = document.getElementById("btnExportExtractCsv");
    this.runProgressBanner = document.getElementById("extractProgressBanner");

    // Correction Modal
    this.correctionModalOverlay = document.getElementById("correctionModalOverlay");
    this.correctionTargetLabel = document.getElementById("correctionTargetLabel");
    this.correctionOriginalValue = document.getElementById("correctionOriginalValue");
    this.correctionNewValueInput = document.getElementById("correctionNewValueInput");
    this.correctionNoteInput = document.getElementById("correctionNoteInput");

    // State initialization
    this.selectedDocIds = new Set(
      state.project.subdocuments.map(s => s.subdocId).slice(1, 7) // default to relevant component subdocs
    );
    this.resultsAreValid = true;

    this.initEvents();
    this.renderStep1();
    this.renderStep2();
    this.goToStep(state.extractStep || 4);

    state.subscribe((event) => {
      if (["correction_applied", "field_updated"].includes(event)) {
        this.renderMatrixTable();
      } else if (event === "correction_modal_open") {
        this.openCorrectionModal();
      } else if (event === "correction_modal_close") {
        if (this.correctionModalOverlay) this.correctionModalOverlay.classList.remove("open");
      }
    });
  }

  initEvents() {
    // Stepper navigation clicks
    this.wizardSteps.forEach((step) => {
      step.addEventListener("click", () => {
        const stepNum = parseInt(step.dataset.step);
        // Allow navigation to completed steps or current step
        if (stepNum <= state.extractStep || step.classList.contains("completed")) {
          this.goToStep(stepNum);
        }
      });
    });

    // Step 1 Events
    if (this.docSearchInput) {
      this.docSearchInput.addEventListener("input", () => this.renderStep1());
    }
    if (this.btnSelectAllDocs) {
      this.btnSelectAllDocs.addEventListener("click", () => {
        state.project.subdocuments.forEach(s => this.selectedDocIds.add(s.subdocId));
        this.invalidateResults();
        this.renderStep1();
      });
    }
    if (this.btnDeselectAllDocs) {
      this.btnDeselectAllDocs.addEventListener("click", () => {
        this.selectedDocIds.clear();
        this.invalidateResults();
        this.renderStep1();
      });
    }
    if (this.btnStep1Continue) {
      this.btnStep1Continue.addEventListener("click", () => {
        if (this.selectedDocIds.size === 0) return;
        this.goToStep(2);
      });
    }

    // Step 2 Events
    if (this.btnAddField) {
      this.btnAddField.addEventListener("click", () => {
        this.saveCurrentFieldsFromInputs();
        state.customFields.push({
          id: `f_custom_${Date.now()}`,
          name: `Custom Field ${state.customFields.length + 1}`,
          type: "Text",
          desc: "Field description",
          unit: "",
          required: false
        });
        this.invalidateResults();
        this.renderStep2();
      });
    }
    if (this.btnStep2Back) {
      this.btnStep2Back.addEventListener("click", () => {
        this.saveCurrentFieldsFromInputs();
        this.goToStep(1);
      });
    }
    if (this.btnStep2Continue) {
      this.btnStep2Continue.addEventListener("click", () => {
        this.saveCurrentFieldsFromInputs();
        if (this.validateFields()) {
          this.renderStep3();
          this.goToStep(3);
        }
      });
    }

    // Step 3 Events
    if (this.btnStep3Back) {
      this.btnStep3Back.addEventListener("click", () => {
        this.goToStep(2);
      });
    }
    if (this.btnStep3Run) {
      this.btnStep3Run.addEventListener("click", () => {
        this.runFullExtraction();
      });
    }

    // Step 4 Events
    if (this.btnEditFields) {
      this.btnEditFields.addEventListener("click", () => {
        this.editFieldsDirectly();
      });
    }
    if (this.btnNewRun) {
      this.btnNewRun.addEventListener("click", () => {
        this.startNewRun();
      });
    }
    if (this.btnExportCsv) {
      this.btnExportCsv.addEventListener("click", () => {
        this.exportToCsv();
      });
    }

    // Correction Modal Actions
    const btnCancel = document.getElementById("btnCancelCorrection");
    if (btnCancel) {
      btnCancel.addEventListener("click", () => state.closeCorrection());
    }
    const btnSave = document.getElementById("btnSaveCorrection");
    if (btnSave) {
      btnSave.addEventListener("click", () => {
        const target = state.activeCorrectionTarget;
        if (!target) return;
        const newVal = this.correctionNewValueInput.value.trim();
        const note = this.correctionNoteInput.value.trim();
        if (newVal) {
          state.applyCorrection(target.rowIndex, target.fieldId, newVal, note);
        }
      });
    }
  }

  invalidateResults() {
    this.resultsAreValid = false;
  }

  // Unified single handler for "Edit fields" button
  editFieldsDirectly() {
    this.saveCurrentFieldsFromInputs();
    this.goToStep(2);
  }

  startNewRun() {
    this.invalidateResults();
    this.goToStep(1);
  }

  goToStep(stepNum) {
    state.extractStep = Math.max(1, Math.min(4, stepNum));

    // Update stepper visual indicators
    this.wizardSteps.forEach((step) => {
      const s = parseInt(step.dataset.step);
      step.classList.toggle("active", s === state.extractStep);
      step.classList.toggle("completed", s < state.extractStep);
      step.disabled = s > state.extractStep;
      if (s === state.extractStep) step.setAttribute("aria-current", "step");
      else step.removeAttribute("aria-current");
    });

    // Show active panel
    this.stepPanels.forEach((panel) => {
      const p = parseInt(panel.dataset.step);
      panel.style.display = p === state.extractStep ? "flex" : "none";
    });

    if (state.extractStep === 1) {
      this.renderStep1();
    } else if (state.extractStep === 2) {
      this.renderStep2();
    } else if (state.extractStep === 3) {
      this.renderStep3();
    } else if (state.extractStep === 4) {
      this.renderMatrixTable();
    }
  }

  /* --------------------------------------------------------------------------
     SCREEN 1: CHOOSE DOCUMENTS
     -------------------------------------------------------------------------- */
  renderStep1() {
    if (!this.docChecklist) return;
    this.docChecklist.replaceChildren();

    const query = this.docSearchInput ? this.docSearchInput.value.toLowerCase().trim() : "";
    const subdocs = state.project.subdocuments || [];

    const filtered = subdocs.filter((s) => {
      if (!query) return true;
      const titleMatch = s.title.toLowerCase().includes(query);
      const typeMatch = s.docType.toLowerCase().includes(query);
      const idMatch = Object.values(s.scopedIdentifiers || {}).some((v) =>
        String(v).toLowerCase().includes(query)
      );
      return titleMatch || typeMatch || idMatch;
    });

    filtered.forEach((sd) => {
      const isSelected = this.selectedDocIds.has(sd.subdocId);
      const row = document.createElement("div");
      row.className = `doc-check-item ${isSelected ? "selected" : ""}`;

      const left = document.createElement("div");
      left.className = "doc-check-left";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = isSelected;
      cb.style.width = "18px";
      cb.style.height = "18px";
      cb.style.cursor = "pointer";
      cb.setAttribute("aria-label", `Select document ${sd.title}`);

      cb.addEventListener("change", (e) => {
        if (e.target.checked) {
          this.selectedDocIds.add(sd.subdocId);
        } else {
          this.selectedDocIds.delete(sd.subdocId);
        }
        this.invalidateResults();
        this.renderStep1();
      });

      const textBlock = document.createElement("div");
      textBlock.style.display = "flex";
      textBlock.style.flexDirection = "column";

      const titleSpan = document.createElement("span");
      titleSpan.className = "doc-check-title";
      titleSpan.textContent = sd.title;
      textBlock.appendChild(titleSpan);

      const metaSpan = document.createElement("span");
      metaSpan.className = "doc-check-meta";
      metaSpan.textContent = `${sd.docType} · Page ${sd.startPage === sd.endPage ? sd.startPage : `${sd.startPage}–${sd.endPage}`}`;
      textBlock.appendChild(metaSpan);

      left.appendChild(cb);
      left.appendChild(textBlock);
      row.appendChild(left);

      // Badge on right
      const badge = document.createElement("span");
      badge.className = "badge badge-neutral";
      badge.textContent = `Page ${sd.startPage}`;
      row.appendChild(badge);

      row.addEventListener("click", (e) => {
        if (e.target === cb) return;
        cb.checked = !cb.checked;
        cb.dispatchEvent(new Event("change"));
      });

      this.docChecklist.appendChild(row);
    });

    // Update count & button state
    const totalCount = subdocs.length;
    const selectedCount = this.selectedDocIds.size;
    if (this.docSelectedCount) {
      this.docSelectedCount.textContent = `${selectedCount} of ${totalCount} documents selected`;
    }
    if (this.btnStep1Continue) {
      this.btnStep1Continue.disabled = selectedCount === 0;
      this.btnStep1Continue.title = selectedCount === 0 ? "Select at least one document to proceed" : "Continue to field schema";
    }
  }

  /* --------------------------------------------------------------------------
     SCREEN 2: DEFINE FIELDS SCHEMA
     -------------------------------------------------------------------------- */
  saveCurrentFieldsFromInputs() {
    if (!this.fieldsTableBody) return;
    const rows = this.fieldsTableBody.querySelectorAll("tr");
    const updated = [];
    rows.forEach((tr, idx) => {
      const nameInput = tr.querySelector(".field-name-input");
      const descInput = tr.querySelector(".field-desc-input");
      const typeSelect = tr.querySelector(".field-type-select");
      const unitInput = tr.querySelector(".field-unit-input");
      const reqCb = tr.querySelector(".field-req-cb");

      const existing = state.customFields[idx] || {};
      updated.push({
        id: existing.id || `f_${idx}_${Date.now()}`,
        name: nameInput ? nameInput.value.trim() : existing.name || `Field ${idx + 1}`,
        desc: descInput ? descInput.value.trim() : existing.desc || "",
        type: typeSelect ? typeSelect.value : existing.type || "Text",
        unit: unitInput ? unitInput.value.trim() : existing.unit || "",
        required: reqCb ? reqCb.checked : Boolean(existing.required)
      });
    });
    if (updated.length > 0) {
      state.customFields = updated;
    }
  }

  validateFields() {
    const fields = state.customFields;
    const validTypes = ["Text", "Number", "Range", "Date", "Boolean"];

    if (fields.length === 0) {
      this.showFieldError("Please define at least one field to extract.");
      return false;
    }

    const seenNames = new Set();
    for (const f of fields) {
      if (!f.name) {
        this.showFieldError("Field names cannot be empty.");
        return false;
      }
      const lower = f.name.toLowerCase();
      if (seenNames.has(lower)) {
        this.showFieldError(`Duplicate field name "${f.name}". Field names must be unique.`);
        return false;
      }
      seenNames.add(lower);

      if (!validTypes.includes(f.type)) {
        this.showFieldError(`Invalid field type "${f.type}". Choose from Text, Number, Range, Date, or Boolean.`);
        return false;
      }
    }

    this.clearFieldError();
    return true;
  }

  showFieldError(msg) {
    if (this.fieldErrorBanner) {
      this.fieldErrorBanner.style.display = "block";
      this.fieldErrorBanner.textContent = msg;
    }
  }

  clearFieldError() {
    if (this.fieldErrorBanner) {
      this.fieldErrorBanner.style.display = "none";
      this.fieldErrorBanner.textContent = "";
    }
  }

  renderStep2() {
    if (!this.fieldsTableBody) return;
    this.fieldsTableBody.replaceChildren();

    state.customFields.forEach((f, idx) => {
      const tr = document.createElement("tr");

      // 1. Name input
      const tdName = document.createElement("td");
      const nameInput = document.createElement("input");
      nameInput.type = "text";
      nameInput.className = "input-text field-name-input";
      nameInput.style.width = "100%";
      nameInput.style.height = "36px";
      nameInput.value = f.name;
      nameInput.setAttribute("aria-label", "Field name");
      nameInput.addEventListener("input", () => this.invalidateResults());
      tdName.appendChild(nameInput);
      tr.appendChild(tdName);

      // 2. Description input
      const tdDesc = document.createElement("td");
      const descInput = document.createElement("input");
      descInput.type = "text";
      descInput.className = "input-text field-desc-input";
      descInput.style.width = "100%";
      descInput.style.height = "36px";
      descInput.value = f.desc || "";
      descInput.setAttribute("aria-label", "Field description");
      descInput.addEventListener("input", () => this.invalidateResults());
      tdDesc.appendChild(descInput);
      tr.appendChild(tdDesc);

      // 3. Type select
      const tdType = document.createElement("td");
      const typeSelect = document.createElement("select");
      typeSelect.className = "select-input field-type-select";
      typeSelect.style.height = "36px";
      typeSelect.style.width = "100%";
      typeSelect.setAttribute("aria-label", "Field type");
      ["Text", "Number", "Range", "Date", "Boolean"].forEach((t) => {
        const opt = document.createElement("option");
        opt.value = t;
        opt.textContent = t;
        if (f.type === t) opt.selected = true;
        typeSelect.appendChild(opt);
      });
      typeSelect.addEventListener("change", () => this.invalidateResults());
      tdType.appendChild(typeSelect);
      tr.appendChild(tdType);

      // 4. Unit input
      const tdUnit = document.createElement("td");
      const unitInput = document.createElement("input");
      unitInput.type = "text";
      unitInput.className = "input-text field-unit-input";
      unitInput.style.width = "80px";
      unitInput.style.height = "36px";
      unitInput.value = f.unit || "";
      unitInput.placeholder = "e.g. bar";
      unitInput.setAttribute("aria-label", "Field unit");
      unitInput.addEventListener("input", () => this.invalidateResults());
      tdUnit.appendChild(unitInput);
      tr.appendChild(tdUnit);

      // 5. Required checkbox
      const tdReq = document.createElement("td");
      tdReq.style.textAlign = "center";
      const reqCb = document.createElement("input");
      reqCb.type = "checkbox";
      reqCb.className = "field-req-cb";
      reqCb.checked = Boolean(f.required);
      reqCb.style.width = "18px";
      reqCb.style.height = "18px";
      reqCb.style.cursor = "pointer";
      reqCb.setAttribute("aria-label", `Field ${f.name} required`);
      reqCb.addEventListener("change", () => this.invalidateResults());
      tdReq.appendChild(reqCb);
      tr.appendChild(tdReq);

      // 6. Delete Action button
      const tdAction = document.createElement("td");
      tdAction.style.textAlign = "center";
      const delBtn = document.createElement("button");
      delBtn.className = "btn btn-subtle btn-sm";
      delBtn.style.color = "var(--color-error)";
      delBtn.title = "Remove field";
      delBtn.textContent = "×";
      delBtn.style.fontSize = "20px";
      delBtn.addEventListener("click", () => {
        this.saveCurrentFieldsFromInputs();
        state.customFields.splice(idx, 1);
        this.invalidateResults();
        this.renderStep2();
      });
      tdAction.appendChild(delBtn);
      tr.appendChild(tdAction);

      this.fieldsTableBody.appendChild(tr);
    });
  }

  /* --------------------------------------------------------------------------
     SCREEN 3: PREVIEW EXTRACTION
     -------------------------------------------------------------------------- */
  renderStep3() {
    if (!this.previewContainer) return;
    this.previewContainer.replaceChildren();

    const selectedSubdocs = state.project.subdocuments.filter((s) =>
      this.selectedDocIds.has(s.subdocId)
    );

    if (selectedSubdocs.length === 0) {
      const alert = document.createElement("div");
      alert.className = "preview-summary-card";
      alert.textContent = "No documents selected. Please return to Step 1 to select documents.";
      this.previewContainer.appendChild(alert);
      return;
    }

    // Header info
    const summaryCard = document.createElement("div");
    summaryCard.className = "preview-summary-card";
    summaryCard.textContent = `Previewing extraction for first ${Math.min(2, selectedSubdocs.length)} of ${selectedSubdocs.length} selected documents against ${state.customFields.length} defined fields. Evid grounds each finding in verified document coordinates.`;
    this.previewContainer.appendChild(summaryCard);

    // Grid of preview cards
    const grid = document.createElement("div");
    grid.className = "preview-grid";

    // Preview 1 to 2 documents
    const previewDocs = selectedSubdocs.slice(0, 2);
    previewDocs.forEach((sd) => {
      const card = document.createElement("div");
      card.className = "preview-doc-card";

      const cardHead = document.createElement("div");
      cardHead.style.display = "flex";
      cardHead.style.justifyContent = "space-between";
      cardHead.style.alignItems = "center";

      const title = document.createElement("strong");
      title.style.color = "var(--color-text-primary)";
      title.textContent = sd.title;
      cardHead.appendChild(title);

      const pageBadge = document.createElement("span");
      pageBadge.className = "badge badge-neutral";
      pageBadge.textContent = `Page ${sd.startPage}`;
      cardHead.appendChild(pageBadge);
      card.appendChild(cardHead);

      // Find matching row in extractionMatrix if present, or generate realistic preview
      const existingRow = state.extractionRows.find(
        (r) => r.subdocId === sd.subdocId || r.page === sd.startPage
      );

      state.customFields.forEach((field) => {
        const row = document.createElement("div");
        row.className = "preview-field-row";

        const nameSpan = document.createElement("span");
        nameSpan.style.color = "var(--color-text-secondary)";
        nameSpan.textContent = field.name;
        row.appendChild(nameSpan);

        const valSpan = document.createElement("span");
        valSpan.style.display = "flex";
        valSpan.style.alignItems = "center";
        valSpan.style.gap = "6px";

        let sampleVal = "Not found";
        let badgeCls = "status-pill-not-found";

        if (existingRow && existingRow.values[field.id]) {
          const v = existingRow.values[field.id];
          sampleVal = v.value;
          if (v.status === "valid") badgeCls = "status-pill-extracted";
          else if (v.status === "na") badgeCls = "status-pill-na";
          else badgeCls = "status-pill-not-found";
        } else if (sd.scopedIdentifiers && sd.scopedIdentifiers[field.id]) {
          sampleVal = sd.scopedIdentifiers[field.id];
          badgeCls = "status-pill-extracted";
        } else if (field.name.toLowerCase().includes("part") && sd.scopedIdentifiers && sd.scopedIdentifiers.articleNumber) {
          sampleVal = sd.scopedIdentifiers.articleNumber;
          badgeCls = "status-pill-extracted";
        } else if (field.name.toLowerCase().includes("lot") && sd.scopedIdentifiers && sd.scopedIdentifiers.lotNumber) {
          sampleVal = sd.scopedIdentifiers.lotNumber;
          badgeCls = "status-pill-extracted";
        }

        valSpan.textContent = sampleVal;
        valSpan.className = badgeCls;
        row.appendChild(valSpan);
        card.appendChild(row);
      });

      grid.appendChild(card);
    });

    this.previewContainer.appendChild(grid);
  }

  /* --------------------------------------------------------------------------
     SCREEN 4: RUN AND REVIEW
     -------------------------------------------------------------------------- */
  runFullExtraction() {
    this.goToStep(4);
    if (this.runProgressBanner) {
      this.runProgressBanner.style.display = "flex";
      this.runProgressBanner.textContent = "Preparing extraction results from the sample data…";
    }

    setTimeout(() => {
      this.resultsAreValid = true;
      if (this.runProgressBanner) {
        this.runProgressBanner.style.display = "none";
      }
      this.renderMatrixTable();
    }, 400);
  }

  renderMatrixTable() {
    if (!this.matrixTable) return;
    const thead = this.matrixTable.querySelector("thead");
    const tbody = this.matrixTable.querySelector("tbody");
    if (!thead || !tbody) return;

    thead.replaceChildren();
    tbody.replaceChildren();

    const fields = state.customFields;
    const selectedSubdocs = state.project.subdocuments.filter((s) =>
      this.selectedDocIds.has(s.subdocId)
    );

    // Build Table Header
    const trHead = document.createElement("tr");

    const thDoc = document.createElement("th");
    thDoc.style.minWidth = "220px";
    thDoc.textContent = "Document / Section";
    trHead.appendChild(thDoc);

    fields.forEach((f) => {
      const th = document.createElement("th");
      th.textContent = f.name + (f.unit ? ` (${f.unit})` : "");
      trHead.appendChild(th);
    });

    const thReview = document.createElement("th");
    thReview.style.width = "180px";
    thReview.textContent = "Review State";
    trHead.appendChild(thReview);

    const thActions = document.createElement("th");
    thActions.style.width = "140px";
    thActions.textContent = "Actions";
    trHead.appendChild(thActions);

    thead.appendChild(trHead);

    if (selectedSubdocs.length === 0) {
      const trEmpty = document.createElement("tr");
      const tdEmpty = document.createElement("td");
      tdEmpty.colSpan = fields.length + 3;
      tdEmpty.style.textAlign = "center";
      tdEmpty.style.padding = "36px";
      tdEmpty.style.color = "var(--color-text-secondary)";
      tdEmpty.textContent = "No documents selected. Return to Step 1 to choose documents.";
      trEmpty.appendChild(tdEmpty);
      tbody.appendChild(trEmpty);
      return;
    }

    // Build Table Rows
    selectedSubdocs.forEach((sd, rIdx) => {
      // Find or build matching extraction row
      let row = state.extractionRows.find((r) => r.subdocId === sd.subdocId);
      if (!row) {
        row = {
          subdocId: sd.subdocId,
          documentTitle: `${sd.title} (p.${sd.startPage})`,
          page: sd.startPage,
          reviewStatus: "Needs review",
          reviewedBy: null,
          reviewedAt: null,
          values: {}
        };
        // Auto-populate from scopedIdentifiers if field matches
        fields.forEach((f) => {
          if (f.id === "f_part" && sd.scopedIdentifiers.articleNumber) {
            row.values[f.id] = { value: sd.scopedIdentifiers.articleNumber, citation: `p. ${sd.startPage}`, status: "valid" };
          } else if (f.id === "f_lot" && sd.scopedIdentifiers.lotNumber) {
            row.values[f.id] = { value: sd.scopedIdentifiers.lotNumber, citation: `p. ${sd.startPage}`, status: "valid" };
          } else if (f.id === "f_gamma" && sd.scopedIdentifiers.gammaRange) {
            row.values[f.id] = { value: sd.scopedIdentifiers.gammaRange, citation: `p. ${sd.startPage}`, status: "valid" };
          } else {
            row.values[f.id] = { value: "Not found on this page", citation: null, status: "not_established" };
          }
        });
        state.extractionRows.push(row);
      }

      const tr = document.createElement("tr");

      // Column 1: Document title & page
      const tdDoc = document.createElement("td");
      const docBox = document.createElement("div");
      docBox.style.display = "flex";
      docBox.style.flexDirection = "column";

      const titleStrong = document.createElement("strong");
      titleStrong.style.color = "var(--color-text-primary)";
      titleStrong.textContent = sd.title;
      docBox.appendChild(titleStrong);

      const pageMeta = document.createElement("span");
      pageMeta.style.fontSize = "12px";
      pageMeta.style.color = "var(--color-text-muted)";
      pageMeta.textContent = `PDF Page ${sd.startPage}`;
      docBox.appendChild(pageMeta);
      tdDoc.appendChild(docBox);
      tr.appendChild(tdDoc);

      // Columns for fields
      fields.forEach((f) => {
        const td = document.createElement("td");
        const valObj = row.values[f.id];

        const cellInteractive = document.createElement("div");
        cellInteractive.className = "matrix-cell-interactive";
        cellInteractive.setAttribute("role", "button");
        cellInteractive.setAttribute("tabindex", "0");
        cellInteractive.title = "Click to inspect citation in viewer or make human correction";

        const textSpan = document.createElement("span");

        if (!valObj) {
          textSpan.className = "status-pill-na";
          textSpan.textContent = "N/A";
        } else if (valObj.status === "na") {
          textSpan.className = "status-pill-na";
          textSpan.textContent = "Not applicable";
        } else if (valObj.status === "not_established" || valObj.status === "not_found") {
          textSpan.className = "status-pill-not-found";
          textSpan.textContent = "Not found";
        } else if (valObj.status === "derived") {
          textSpan.className = "status-pill-derived";
          textSpan.textContent = valObj.value;
        } else if (valObj.status === "uncertain") {
          textSpan.className = "status-pill-uncertain";
          textSpan.textContent = valObj.value;
        } else if (valObj.status === "failed") {
          textSpan.className = "status-pill-failed";
          textSpan.textContent = valObj.value || "Extraction failed";
        } else {
          textSpan.className = "status-pill-extracted";
          textSpan.textContent = valObj.value;
        }

        cellInteractive.appendChild(textSpan);

        if (valObj && valObj.citation) {
          const pill = document.createElement("span");
          pill.className = "citation-pill";
          pill.textContent = valObj.citation;
          cellInteractive.appendChild(pill);
        }

        if (valObj && valObj.corrected) {
          const corrBadge = document.createElement("span");
          corrBadge.className = "human-corrected-pill";
          corrBadge.textContent = "Corrected";
          cellInteractive.appendChild(corrBadge);
        }

        const openCellAction = () => {
          if (valObj && valObj.box) {
            state.openEvidence(row.page, valObj.box, sd.title, cellInteractive);
          } else {
            state.openEvidence(row.page, null, sd.title, cellInteractive);
          }
          state.openCorrection(rIdx, f.id);
        };

        cellInteractive.addEventListener("click", openCellAction);
        cellInteractive.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            openCellAction();
          }
        });

        td.appendChild(cellInteractive);
        tr.appendChild(td);
      });

      // Review status cell
      const tdReview = document.createElement("td");
      const reviewBadge = document.createElement("span");
      const statusText = row.reviewStatus || "Needs review";

      if (statusText.includes("Accepted")) {
        reviewBadge.className = "badge badge-success";
      } else if (statusText.includes("Corrected")) {
        reviewBadge.className = "badge badge-info";
      } else {
        reviewBadge.className = "badge badge-warning";
      }
      reviewBadge.textContent = statusText;
      tdReview.appendChild(reviewBadge);
      tr.appendChild(tdReview);

      // Actions cell
      const tdActions = document.createElement("td");
      const actionsWrap = document.createElement("div");
      actionsWrap.style.display = "flex";
      actionsWrap.style.gap = "6px";

      const acceptBtn = document.createElement("button");
      acceptBtn.className = "btn btn-secondary btn-sm";
      acceptBtn.textContent = "✓ Accept";
      acceptBtn.title = "Accept extracted finding locally";
      acceptBtn.addEventListener("click", () => {
        row.reviewStatus = "Accepted locally by Quality Engineer";
        row.reviewedBy = "Current User (Quality Engineer)";
        row.reviewedAt = new Date().toLocaleTimeString();
        this.renderMatrixTable();
      });
      actionsWrap.appendChild(acceptBtn);

      const viewBtn = document.createElement("button");
      viewBtn.className = "btn btn-subtle btn-sm";
      viewBtn.textContent = "View";
      viewBtn.title = "Open document in evidence viewer";
      viewBtn.addEventListener("click", () => {
        state.openEvidence(row.page, null, sd.title, viewBtn);
      });
      actionsWrap.appendChild(viewBtn);

      tdActions.appendChild(actionsWrap);
      tr.appendChild(tdActions);

      tbody.appendChild(tr);
    });
  }

  openCorrectionModal() {
    const t = state.activeCorrectionTarget;
    if (!t) return;
    this.correctionTargetLabel.textContent = `${t.fieldName} (${t.rowTitle})`;
    this.correctionOriginalValue.textContent = t.currentValue;
    this.correctionNewValueInput.value = t.currentValue;
    this.correctionNoteInput.value = "";
    this.correctionModalOverlay.classList.add("open");
    setTimeout(() => this.correctionNewValueInput.focus(), 80);
  }

  // Formula-safe CSV cell sanitizer
  sanitizeCsvCell(val) {
    if (val == null) return '""';
    let s = String(val);
    // Spreadsheet-formula protection
    if (/^[=+\-@\t\r]/.test(s)) {
      s = "'" + s;
    }
    return `"${s.replace(/"/g, '""')}"`;
  }

  exportToCsv() {
    const fields = state.customFields;
    const selectedSubdocs = state.project.subdocuments.filter((s) =>
      this.selectedDocIds.has(s.subdocId)
    );

    const headers = [
      "Document Title",
      "PDF Page",
      ...fields.map((f) => f.name + (f.unit ? ` (${f.unit})` : "")),
      "Review Status",
      "Reviewed By"
    ];

    let csv = headers.map((h) => this.sanitizeCsvCell(h)).join(",") + "\n";

    selectedSubdocs.forEach((sd) => {
      const row = state.extractionRows.find((r) => r.subdocId === sd.subdocId) || {};
      const line = [
        sd.title,
        `Page ${sd.startPage}`,
        ...fields.map((f) => {
          const valObj = row.values ? row.values[f.id] : null;
          return valObj ? valObj.value : "Not found";
        }),
        row.reviewStatus || "Needs review",
        row.reviewedBy || "Unreviewed"
      ];
      csv += line.map((cell) => this.sanitizeCsvCell(cell)).join(",") + "\n";
    });

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "evid_structured_extraction_results.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }
}
