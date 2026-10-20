/* ==========================================================================
   EVID CENTRAL REACTIVE APPLICATION STATE
   - Single source of truth for all workflows
   - Grounded citations and verification bounds
   - Modal focus trapping, Escape handling, and focus restoration
   - Saved findings persistence
   ========================================================================== */

class AppStateManager {
  constructor() {
    this.project = {
      projectId: "local_workspace", projectName: "My workspace", isSampleProject: false,
      masterFile: null, subdocuments: [], extractionMatrix: {fields: [], rows: []}
    };
    this.uploadedDocuments = [];
    this.activeTab = "documents"; // 'documents' | 'ask' | 'extract' | 'compare'
    this.sidebarCollapsed = false;

    // Documents Screen State
    this.expandedBundles = new Set();
    this.docSearchQuery = "";
    this.docTypeFilter = "all";
    this.docStatusFilter = "all";
    this.editingSubdoc = null;

    // Ask Grounded QA State
    this.sourceScope = "all";
    this.selectedSources = new Set();
    this.conversation = [];
    this.isAsking = false;
    this.savedFindings = [];
    this.issueReports = [];

    // Evidence Viewer State
    this.isViewerOpen = false;
    this.viewerDoc = "";
    this.viewerFileId = null;
    this.viewerPage = 1;
    this.viewerBox = null;
    this.viewerZoom = 1.0;
    this.showHighlights = true;
    this.showThumbnails = true;
    this.showTextDrawer = false;
    this.lastFocusedElement = null; // For keyboard accessibility return-focus

    // Extraction Wizard State
    this.extractStep = 1;
    this.customFields = [];
    this.extractionRows = [];

    // Modals & Dialog Focus Management
    this.activeModal = null;
    this.isUploadModalOpen = false;
    this.isCalcModalOpen = false;
    this.activeCalculation = null;
    this.isCorrectionModalOpen = false;
    this.activeCorrectionTarget = null;
    this.isSettingsModalOpen = false;
    this.isHelpModalOpen = false;

    // Browser tabs share the server's HttpOnly workspace cookie. BroadcastChannel
    // makes a completed upload or clear visible in the other open tabs without
    // exposing that cookie to JavaScript.
    this.workspaceChannel = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel("evid-workspace");
    this.workspaceChannel?.addEventListener("message", (event) => {
      if (event.data?.type === "documents_changed") this.loadUploadedDocuments();
    });

    // Event Subscribers
    this.listeners = [];

    this.initGlobalKeyboardHandlers();
  }

  subscribe(listener) {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter(l => l !== listener);
    };
  }

  notify(event, payload) {
    this.listeners.forEach(l => l(event, payload, this));
  }

  setActiveTab(tabName) {
    this.activeTab = tabName;
    this.notify("tab_change", tabName);
  }

  toggleSidebar() {
    this.sidebarCollapsed = !this.sidebarCollapsed;
    this.notify("sidebar_toggle", this.sidebarCollapsed);
  }

  // A section always belongs to one original file. Sample workflows keep their
  // existing section IDs; uploaded IDs are namespaced by the file's content hash.
  getDocuments() {
    const sample = this.project.masterFile ? [{
      ...this.project.masterFile,
      docId: this.project.masterFile.fileId,
      isSample: true,
      pageImageBase: "public/pages",
      pageText: this.project.accessiblePageText || {},
      subdocuments: this.project.subdocuments,
    }] : [];
    return [...sample, ...this.uploadedDocuments];
  }

  getDocument(fileId) {
    return this.getDocuments().find(doc => doc.fileId === fileId || doc.docId === fileId);
  }

  registerUploadedDocument(data, notify = true) {
    if (!/^[a-f0-9]{64}$/.test(data.docId || "") || !Number.isInteger(data.totalPages) || data.totalPages < 1 ||
        ![ `public/pages/${data.docId}`, `/api/documents/${data.docId}/pages` ].includes(data.pageImageBase) || !data.filename) {
      throw new Error("The server returned an incomplete document record. Please retry the upload.");
    }
    const existing = this.uploadedDocuments.find(doc => doc.fileId === data.docId);
    if (existing) {
      // A re-upload can supply native text that older saved renders lacked.
      if (data.pageText && Object.keys(data.pageText).length) {
        existing.pageText = data.pageText;
        existing.textAvailable = data.textAvailable;
      }
      return existing;
    }
    const file = {
      ...data,
      fileId: data.docId,
      isSample: false,
      pageText: data.pageText || {},
      subdocuments: (data.subdocuments || []).map((section, index) => ({
        ...section,
        subdocId: `${data.docId}_sub_${index + 1}`,
        parentFileId: data.docId,
      })),
    };
    file.importedSections = JSON.parse(JSON.stringify(file.subdocuments));
    this.uploadedDocuments.push(file);
    this.expandedBundles.add(file.fileId);
    if (notify) this.notify("document_added", file);
    return file;
  }

  async loadUploadedDocuments() {
    this.notify("library_loading");
    try {
      const response = await fetch("/api/documents");
      if (!response.ok) throw new Error("Saved uploads could not be loaded. Check that the CiteCanvas server is running and refresh the page.");
      const data = await response.json();
      if (!Array.isArray(data.documents)) throw new Error("The saved-file list is invalid.");
      // Reconcile instead of appending: another tab may have cleared the
      // workspace since this page initially loaded.
      this.uploadedDocuments = [];
      data.documents.forEach(doc => this.registerUploadedDocument(doc, false));
      this.notify("document_added");
      this.notify("library_loaded");
    } catch (error) {
      this.notify("library_load_error", error.message);
    }
  }

  announceWorkspaceChanged() {
    this.workspaceChannel?.postMessage({ type: "documents_changed" });
  }

  async clearWorkspace() {
    const response = await fetch("/api/workspace/clear", { method: "POST" });
    if (!response.ok) {
      let message = "This workspace could not be cleared.";
      try { message = (await response.json()).error || message; } catch (_) {}
      throw new Error(message);
    }
    this.uploadedDocuments = [];
    this.expandedBundles.clear();
    this.conversation = [];
    this.extractionRows = [];
    this.notify("document_added");
    this.announceWorkspaceChanged();
  }

  // Existing sample citations default explicitly to the sample source, even
  // when an uploaded document was the last file opened in the viewer.
  openEvidence(pageNumber, box = null, docTitle = "", triggerElement = null, fileId = this.project.masterFile?.fileId) {
    const file = this.getDocument(fileId);
    if (!file) throw new Error("This source file is not available in the library.");
    this.isViewerOpen = true;
    const changedFile = this.viewerFileId !== file.fileId;
    this.viewerFileId = file.fileId;
    this.viewerPage = this.clampViewerPage(pageNumber);
    this.viewerBox = box;
    this.viewerDoc = docTitle;
    if (changedFile) this.viewerZoom = 1;
    if (triggerElement) this.lastFocusedElement = triggerElement;
    this.notify("evidence_opened", { pageNumber: this.viewerPage, box, docTitle, fileId: file.fileId });
  }

  closeEvidence() {
    this.isViewerOpen = false;
    this.viewerBox = null;
    this.notify("evidence_closed");
    if (this.lastFocusedElement && typeof this.lastFocusedElement.focus === "function") {
      this.lastFocusedElement.focus();
    }
  }

  setViewerPage(newPage) {
    const page = this.clampViewerPage(newPage);
    if (page !== this.viewerPage) this.viewerBox = null;
    this.viewerPage = page;
    this.notify("viewer_page_change", page);
  }

  clampViewerPage(value) {
    const total = this.getDocument(this.viewerFileId)?.totalPages || 1;
    const page = Number.parseInt(value, 10);
    return Math.max(1, Math.min(total, Number.isFinite(page) ? page : 1));
  }

  setViewerZoom(zoom) {
    this.viewerZoom = Math.max(0.5, Math.min(2.5, zoom));
    this.notify("viewer_zoom_change", this.viewerZoom);
  }

  toggleHighlights() {
    this.showHighlights = !this.showHighlights;
    this.notify("viewer_highlights_toggle", this.showHighlights);
  }

  toggleThumbnails() {
    this.showThumbnails = !this.showThumbnails;
    this.notify("viewer_thumbnails_toggle", this.showThumbnails);
  }

  toggleTextDrawer() {
    this.showTextDrawer = !this.showTextDrawer;
    this.notify("viewer_text_drawer_toggle", this.showTextDrawer);
  }

  // Calculation Modal
  openCalculation(calcData) {
    this.lastFocusedElement = document.activeElement;
    this.activeCalculation = calcData;
    this.isCalcModalOpen = true;
    this.trapFocusInModal("calcModalOverlay");
    this.notify("calc_modal_open", calcData);
  }

  closeCalculation() {
    this.isCalcModalOpen = false;
    this.activeCalculation = null;
    this.restoreModalFocus();
    this.notify("calc_modal_close");
  }

  // Boundary Review Modal
  openBoundaryReview(subdoc) {
    this.lastFocusedElement = document.activeElement;
    this.editingSubdoc = JSON.parse(JSON.stringify(subdoc));
    this.trapFocusInModal("boundaryModalOverlay");
    this.notify("boundary_modal_open", this.editingSubdoc);
  }

  closeBoundaryReview() {
    this.editingSubdoc = null;
    this.restoreModalFocus();
    this.notify("boundary_modal_close");
  }

  saveBoundaryReview(updatedSubdoc) {
    const owner = this.getDocuments().find(doc => doc.subdocuments.some(section => section.subdocId === updatedSubdoc.subdocId));
    const idx = owner ? owner.subdocuments.findIndex(s => s.subdocId === updatedSubdoc.subdocId) : -1;
    if (idx !== -1) {
      owner.subdocuments[idx] = updatedSubdoc;
      owner.subdocuments[idx].metadataStatus = "User-confirmed";
    }
    this.closeBoundaryReview();
    this.notify("subdoc_updated", updatedSubdoc);
  }

  // Human Correction for Extraction Matrix
  openCorrection(rowIndex, fieldId) {
    this.lastFocusedElement = document.activeElement;
    const row = this.extractionRows[rowIndex];
    const field = this.project.extractionMatrix.fields.find(f => f.id === fieldId) || { name: fieldId };
    this.activeCorrectionTarget = {
      rowIndex,
      fieldId,
      fieldName: field ? field.name : fieldId,
      currentValue: row && row.values[fieldId] ? row.values[fieldId].value : "",
      rowTitle: row ? row.documentTitle : "Extraction Record"
    };
    this.isCorrectionModalOpen = true;
    this.trapFocusInModal("correctionModalOverlay");
    this.notify("correction_modal_open", this.activeCorrectionTarget);
  }

  closeCorrection() {
    this.isCorrectionModalOpen = false;
    this.activeCorrectionTarget = null;
    this.restoreModalFocus();
    this.notify("correction_modal_close");
  }

  applyCorrection(rowIndex, fieldId, newValue, note = "") {
    const row = this.extractionRows[rowIndex];
    if (row && row.values[fieldId]) {
      const orig = row.values[fieldId].value;
      row.values[fieldId].value = newValue;
      row.values[fieldId].corrected = true;
      row.values[fieldId].originalValue = orig;
      row.values[fieldId].correctionNote = note;
      row.reviewStatus = "Corrected locally by Quality Engineer";
      row.reviewedBy = "Current User (Quality Engineer)";
      row.reviewedAt = new Date().toLocaleTimeString();
    }
    this.closeCorrection();
    this.notify("correction_applied", { rowIndex, fieldId, newValue });
  }

  // Accessible Modal Focus Management
  trapFocusInModal(modalId) {
    this.activeModal = document.getElementById(modalId);
    if (!this.activeModal) return;

    setTimeout(() => {
      if (!this.activeModal) return;
      const focusable = this.activeModal.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length > 0) {
        focusable[0].focus();
      }
    }, 50);
  }

  restoreModalFocus() {
    if (this.lastFocusedElement && typeof this.lastFocusedElement.focus === "function") {
      this.lastFocusedElement.focus();
    }
    this.activeModal = null;
  }

  initGlobalKeyboardHandlers() {
    document.addEventListener("keydown", (e) => {
      // Escape closes open modals or evidence viewer
      if (e.key === "Escape") {
        if (this.activeModal?.classList.contains("open")) {
          e.preventDefault();
          // A dialog owns Escape; don't also close the viewer behind it.
          e.stopImmediatePropagation();
          const modalId = this.activeModal.id;
          if (modalId === "uploadModalOverlay" || modalId === "reportModalOverlay") {
            this.notify("modal_close_requested", modalId);
            return;
          }
        }
        if (this.isCalcModalOpen) {
          this.closeCalculation();
        } else if (this.isCorrectionModalOpen) {
          this.closeCorrection();
        } else if (this.editingSubdoc) {
          this.closeBoundaryReview();
        } else if (this.isSettingsModalOpen) {
          this.closeSettings();
        } else if (this.isHelpModalOpen) {
          this.closeHelp();
        }
      }

      // Tab trap inside active modal
      if (e.key === "Tab" && this.activeModal && this.activeModal.classList.contains("open")) {
        const focusable = Array.from(
          this.activeModal.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
          )
        ).filter(el => !el.disabled && el.offsetParent !== null);

        if (focusable.length === 0) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    });
  }

  openSettings() {
    this.lastFocusedElement = document.activeElement;
    this.isSettingsModalOpen = true;
    const m = document.getElementById("settingsModalOverlay");
    if (m) {
      m.classList.add("open");
      this.trapFocusInModal("settingsModalOverlay");
    }
  }

  closeSettings() {
    this.isSettingsModalOpen = false;
    const m = document.getElementById("settingsModalOverlay");
    if (m) m.classList.remove("open");
    this.restoreModalFocus();
  }

  openHelp() {
    this.lastFocusedElement = document.activeElement;
    this.isHelpModalOpen = true;
    const m = document.getElementById("helpModalOverlay");
    if (m) {
      m.classList.add("open");
      this.trapFocusInModal("helpModalOverlay");
    }
  }

  closeHelp() {
    this.isHelpModalOpen = false;
    const m = document.getElementById("helpModalOverlay");
    if (m) m.classList.remove("open");
    this.restoreModalFocus();
  }
}

// Global Singleton Store
const state = new AppStateManager();
window.state = state;
