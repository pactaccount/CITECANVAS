/* ==========================================================================
   EVID FILE UPLOADER CONTROLLER
   - Strict client-side and server-side validation (PDF only, 25MB max, no empty files)
   - Genuine upload/processing/indexing states (NO fake timer-simulated success)
   - Preserves successful files when another fails
   - Updates document counts, adds to library, opens uploaded file
   - Safe DOM rendering via textContent / DOM APIs
   ========================================================================== */

class UploaderController {
  constructor() {
    this.modal = document.getElementById("uploadModalOverlay");
    this.dropzone = document.getElementById("uploadDropzone");
    this.fileInput = document.getElementById("uploadFileInput");
    this.queueList = document.getElementById("uploadQueueList");
    this.btnOpenUpload = document.getElementById("btnTopAddDocs");
    this.btnBannerUpload = document.getElementById("btnBannerUpload");
    this.btnCloseModal = document.getElementById("btnCloseUploadModal");

    this.btnDone = document.getElementById("btnDoneUpload");
    this.activeUploads = new Map();
    this.initEvents();
    document.getElementById("btnFirstUpload")?.addEventListener("click", () => this.open());
    state.subscribe((event, id) => {
      if (event === "modal_close_requested" && id === "uploadModalOverlay") this.close();
    });
  }

  initEvents() {
    this.btnDone?.addEventListener("click", () => this.close());
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && this.modal?.classList.contains("open")) {
        this.close();
      }
    });
    if (this.btnOpenUpload) {
      this.btnOpenUpload.addEventListener("click", () => this.open());
    }
    if (this.btnBannerUpload) {
      this.btnBannerUpload.addEventListener("click", () => this.open());
    }
    if (this.btnCloseModal) {
      this.btnCloseModal.addEventListener("click", () => this.close());
    }

    if (this.dropzone) {
      this.dropzone.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          this.fileInput?.click();
        }
      });
      this.dropzone.addEventListener("click", () => {
        if (this.fileInput) this.fileInput.click();
      });

      this.dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        this.dropzone.classList.add("dragover");
      });

      this.dropzone.addEventListener("dragleave", () => {
        this.dropzone.classList.remove("dragover");
      });

      this.dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        this.dropzone.classList.remove("dragover");
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
          this.handleFiles(e.dataTransfer.files);
        }
      });
    }

    if (this.fileInput) {
      this.fileInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files.length > 0) {
          this.handleFiles(e.target.files);
          this.fileInput.value = ""; // Reset for re-selection
        }
      });
    }
  }

  open() {
    state.lastFocusedElement = document.activeElement;
    state.isUploadModalOpen = true;
    state.trapFocusInModal("uploadModalOverlay");
    if (this.modal) this.modal.classList.add("open");
  }

  close() {
    if (this.modal) this.modal.classList.remove("open");
    state.isUploadModalOpen = false;
    state.restoreModalFocus();
  }

  handleFiles(files) {
    const list = Array.from(files);
    list.forEach((file) => {
      this.processFile(file);
    });
  }

  // Client-side early validation
  validateClient(file) {
    if (file.size === 0) {
      return { valid: false, error: "File is empty (0 bytes). Empty files cannot be ingested." };
    }
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      return { valid: false, error: `Unsupported format '${file.name}'. Evid accepts PDF files (.pdf) only.` };
    }
    const maxBytes = 25 * 1024 * 1024; // 25 MB
    if (file.size > maxBytes) {
      return { valid: false, error: `File exceeds 25 MB limit (${(file.size / (1024 * 1024)).toFixed(1)} MB).` };
    }
    return { valid: true };
  }

  async processFile(file) {
    const uploadId = `upload_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    const row = this.createFileRow(uploadId, file);
    this.queueList.prepend(row);

    // 1. Early client validation
    const clientCheck = this.validateClient(file);
    if (!clientCheck.valid) {
      this.updateRowState(row, "error", clientCheck.error);
      return;
    }

    // 2. Magic bytes check (PDF header %PDF-)
    try {
      const headerBytes = await this.readSlice(file, 0, 5);
      const headerStr = new TextDecoder().decode(headerBytes);
      if (!headerStr.startsWith("%PDF")) {
        this.updateRowState(row, "error", "Invalid or corrupted PDF header. File is unparseable.");
        return;
      }
    } catch (e) {
      this.updateRowState(row, "error", "Unable to read file contents.");
      return;
    }

    const controller = new AbortController();
    this.activeUploads.set(uploadId, controller);
    this.updateRowState(row, "uploading", "Uploading and rendering PDF…");
    row.querySelector(".btn-file-action").onclick = () => {
      controller.abort();
      this.updateRowState(row, "error", "Stopped waiting. The server may already have saved this PDF; refresh the library to check.");
    };

    try {
      const response = await fetch("/api/upload", {
        method: "POST",
        headers: { "X-Filename": encodeURIComponent(file.name) },
        body: file,
        signal: controller.signal,
      });
      if (!response.ok) {
        let message = "The server could not process this PDF.";
        try { message = (await response.json()).error || message; } catch (_) {}
        this.updateRowState(row, "error", message);
        return;
      }
      this.onIngestionSuccess(row, file, await response.json());
    } catch (error) {
      if (error.name !== "AbortError") {
        this.updateRowState(row, "error", "Could not confirm this upload. Check the Evid server and refresh the library before retrying. " + error.message);
      }
    } finally {
      this.activeUploads.delete(uploadId);
    }
  }

  readSlice(file, start, end) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(new Uint8Array(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsArrayBuffer(file.slice(start, end));
    });
  }

  onIngestionSuccess(row, file, docData) {
    const alreadyPresent = Boolean(state.getDocument(docData.docId));
    const documentRecord = state.registerUploadedDocument(docData);
    state.announceWorkspaceChanged();
    // Reveal the source even if an earlier search or review filter was active.
    state.docSearchQuery = "";
    state.docTypeFilter = "all";
    state.docStatusFilter = "all";
    const search = document.getElementById("docSearchInput");
    const type = document.getElementById("docTypeFilter");
    const status = document.getElementById("docStatusFilter");
    if (search) search.value = "";
    if (type) type.value = "all";
    if (status) status.value = "all";
    state.notify("doc_search_changed");
    this.updateRowState(row, alreadyPresent || docData.duplicate ? "duplicate" : "ready",
      alreadyPresent || docData.duplicate ? "Already in library" : "Ready", () => {
        this.close();
        state.setActiveTab("documents");
        state.openEvidence(1, null, documentRecord.filename, this.btnOpenUpload, documentRecord.fileId);
      });
  }

  createFileRow(id, file) {
    const row = document.createElement("div");
    row.className = "upload-file-row";
    row.id = id;

    const info = document.createElement("div");
    info.className = "file-info-group";

    // Clean SVG icon (no emoji)
    const svgIcon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svgIcon.setAttribute("width", "20");
    svgIcon.setAttribute("height", "20");
    svgIcon.setAttribute("viewBox", "0 0 24 24");
    svgIcon.setAttribute("fill", "none");
    svgIcon.setAttribute("stroke", "currentColor");
    svgIcon.setAttribute("stroke-width", "2");
    svgIcon.style.color = "var(--color-primary)";

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z");
    const poly = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    poly.setAttribute("points", "14 2 14 8 20 8");
    svgIcon.appendChild(path);
    svgIcon.appendChild(poly);
    info.appendChild(svgIcon);

    const textCol = document.createElement("div");
    textCol.style.display = "flex";
    textCol.style.flexDirection = "column";

    const nameSpan = document.createElement("span");
    nameSpan.className = "file-name";
    nameSpan.textContent = file.name;
    textCol.appendChild(nameSpan);

    const sizeSpan = document.createElement("span");
    sizeSpan.className = "file-size";
    const mb = file.size / (1024 * 1024);
    sizeSpan.textContent = mb >= 0.1 ? `${mb.toFixed(1)} MB` : `${Math.round(file.size / 1024)} KB`;
    textCol.appendChild(sizeSpan);

    info.appendChild(textCol);
    row.appendChild(info);

    const statusGroup = document.createElement("div");
    statusGroup.className = "file-status-group";

    const badge = document.createElement("span");
    badge.className = "badge badge-info status-badge";
    badge.textContent = "Validating...";
    statusGroup.appendChild(badge);

    const actionBtn = document.createElement("button");
    actionBtn.className = "btn btn-subtle btn-sm btn-file-action";
    actionBtn.textContent = "Cancel";
    actionBtn.onclick = () => row.remove();
    statusGroup.appendChild(actionBtn);

    row.appendChild(statusGroup);
    return row;
  }

  updateRowState(row, stateKey, message, actionCallback = null) {
    const badge = row.querySelector(".status-badge");
    const actionBtn = row.querySelector(".btn-file-action");
    if (!badge || !actionBtn) return;

    badge.textContent = message;

    if (stateKey === "error") {
      badge.className = "badge badge-error status-badge";
      actionBtn.textContent = "Dismiss";
      actionBtn.onclick = () => row.remove();
    } else if (stateKey === "duplicate") {
      badge.className = "badge badge-warning status-badge";
      actionBtn.textContent = "Open";
      if (actionCallback) actionBtn.onclick = actionCallback;
    } else if (stateKey === "uploading") {
      badge.className = "badge badge-info status-badge";
      actionBtn.textContent = "Cancel";
      actionBtn.onclick = () => row.remove();
    } else if (stateKey === "ready") {
      badge.className = "badge badge-success status-badge";
      actionBtn.textContent = "Open File";
      if (actionCallback) actionBtn.onclick = actionCallback;
    }
  }
}
