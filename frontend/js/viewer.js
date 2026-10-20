/* ==========================================================================
   EVID EVIDENCE VIEWER CONTROLLER
   - Single unified viewer for all workflows
   - High-Res Document Stage, verified Bounding Box Overlays
   - Page Filmstrip, Thumbnails, Page-Jump input with Enter & bounds validation
   - Zoom In / Out / Fit / Fullscreen
   - Text toggle drawer with wrapped source text
   - Clears prior file state when opening another file
   - Verified PDF page references (no fabricated printed page claims)
   ========================================================================== */

class EvidenceViewerController {
  constructor() {
    this.container = document.getElementById("evidencePanel");
    this.viewport = document.getElementById("viewerViewport");
    this.stage = document.getElementById("pageStage");
    this.pageImage = document.getElementById("pageImage");
    this.boxLayer = document.getElementById("boxOverlayLayer");
    this.thumbnailsPanel = document.getElementById("thumbnailsPanel");
    this.textDrawer = document.getElementById("viewerTextDrawer");
    this.textDrawerContent = document.getElementById("textDrawerContent");

    this.divider = document.getElementById("resizeDivider");
    this.workspace = document.getElementById("workspaceContainer");

    this.pageIndicator = document.getElementById("viewerPageIndicator");
    this.pageJumpInput = document.getElementById("pageJumpInput");
    this.docTitleEl = document.getElementById("viewerDocTitle");

    this.currentDocument = state.getDocument(state.viewerFileId);
    this.totalPages = this.currentDocument?.totalPages || 0;
    this.currentDocFile = this.currentDocument?.fileId || null;
    this.pageStatus = document.getElementById("viewerPageStatus");

    this.initDividerDrag();
    this.initControls();
    this.initKeyboardShortcuts();
    this.renderThumbnails();
    this.resizeObserver = new ResizeObserver(() => {
      if (state.isViewerOpen) this.applyZoom();
    });
    this.resizeObserver.observe(this.viewport);

    // Subscribe to state changes
    state.subscribe((event, payload) => {
      if (event === "evidence_opened") {
        this.open(payload);
      } else if (event === "evidence_closed") {
        this.close();
      } else if (event === "viewer_page_change") {
        this.renderCurrentPage();
      } else if (event === "viewer_zoom_change") {
        this.applyZoom();
      } else if (event === "viewer_highlights_toggle") {
        this.boxLayer.style.display = state.showHighlights ? "block" : "none";
        this.syncToggleButtons();
      } else if (event === "viewer_thumbnails_toggle") {
        this.thumbnailsPanel.classList.toggle("collapsed", !state.showThumbnails);
        this.syncToggleButtons();
      } else if (event === "viewer_text_drawer_toggle") {
        this.textDrawer.classList.toggle("open", state.showTextDrawer);
        this.syncToggleButtons();
        if (state.showTextDrawer) {
          this.updateTextDrawerContent();
        }
      }
    });
  }

  initControls() {
    this.syncToggleButtons();
    this.pageImage.addEventListener("load", () => {
      this.stage.hidden = false;
      if (this.pageStatus) this.pageStatus.hidden = true;
    });
    this.pageImage.addEventListener("error", () => {
      this.stage.hidden = true;
      this.boxLayer.replaceChildren();
      if (this.pageStatus) {
        this.pageStatus.hidden = false;
        this.pageStatus.textContent = `Could not load PDF page ${state.viewerPage} of ${this.currentDocument?.filename || "the selected file"}. Check the CiteCanvas server and reopen this source.`;
      }
    });
    // Page jump input: handle Enter key and change
    if (this.pageJumpInput) {
      const handleJump = () => {
        let val = parseInt(this.pageJumpInput.value, 10);
        if (isNaN(val) || val < 1) {
          val = 1;
        } else if (val > this.totalPages) {
          val = this.totalPages;
        }
        this.pageJumpInput.value = val;
        state.setViewerPage(val);
      };

      this.pageJumpInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          handleJump();
        }
      });

      this.pageJumpInput.addEventListener("change", () => {
        handleJump();
      });
    }

    // Previous / Next page
    const btnPrev = document.getElementById("btnPrevPage");
    if (btnPrev) {
      btnPrev.addEventListener("click", () => {
        state.setViewerPage(state.viewerPage - 1);
      });
    }

    const btnNext = document.getElementById("btnNextPage");
    if (btnNext) {
      btnNext.addEventListener("click", () => {
        state.setViewerPage(state.viewerPage + 1);
      });
    }

    // Zoom controls
    const btnZoomIn = document.getElementById("btnZoomIn");
    if (btnZoomIn) {
      btnZoomIn.addEventListener("click", () => {
        state.setViewerZoom(state.viewerZoom + 0.15);
      });
    }

    const btnZoomOut = document.getElementById("btnZoomOut");
    if (btnZoomOut) {
      btnZoomOut.addEventListener("click", () => {
        state.setViewerZoom(state.viewerZoom - 0.15);
      });
    }

    const btnZoomReset = document.getElementById("btnZoomReset");
    if (btnZoomReset) {
      btnZoomReset.addEventListener("click", () => {
        this.fitToWidth();
      });
    }

    // Fullscreen toggle
    const btnFullscreen = document.getElementById("btnToggleFullscreen");
    if (btnFullscreen) {
      btnFullscreen.addEventListener("click", () => {
        this.toggleFullscreen();
      });
    }

    // Close button
    const btnClose = document.getElementById("btnCloseEvidence");
    if (btnClose) {
      btnClose.addEventListener("click", () => {
        state.closeEvidence();
      });
    }

    // Toolbar toggle buttons
    const btnToggleHighlights = document.getElementById("btnToggleHighlights");
    if (btnToggleHighlights) {
      btnToggleHighlights.addEventListener("click", () => state.toggleHighlights());
    }

    const btnToggleThumbnails = document.getElementById("btnToggleThumbnails");
    if (btnToggleThumbnails) {
      btnToggleThumbnails.addEventListener("click", () => state.toggleThumbnails());
    }

    const btnToggleTextDrawer = document.getElementById("btnToggleTextDrawer");
    if (btnToggleTextDrawer) {
      btnToggleTextDrawer.addEventListener("click", () => state.toggleTextDrawer());
    }
  }

  syncToggleButtons() {
    const toggles = {
      btnToggleHighlights: state.showHighlights,
      btnToggleThumbnails: state.showThumbnails,
      btnToggleTextDrawer: state.showTextDrawer,
    };
    Object.entries(toggles).forEach(([id, pressed]) => {
      const button = document.getElementById(id);
      button?.classList.toggle("active", pressed);
      button?.setAttribute("aria-pressed", String(pressed));
    });
  }

  fitToWidth() {
    if (!this.viewport || !this.stage) return;
    state.setViewerZoom(1.0);
    this.viewport.scrollTop = 0;
    this.viewport.scrollLeft = 0;
  }

  toggleFullscreen() {
    if (!document.fullscreenElement) {
      this.container.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  }

  open(payload = {}) {
    const source = state.getDocument(payload.fileId);
    if (!source) return;
    this.currentDocument = source;
    this.totalPages = source.totalPages;
    this.currentDocFile = source.fileId;
    this.viewport.scrollTop = 0;
    this.viewport.scrollLeft = 0;
    this.pageImage.removeAttribute("src");
    this.boxLayer.replaceChildren();
    if (this.textDrawerContent) this.textDrawerContent.textContent = "";
    this.renderThumbnails();
    this.syncToggleButtons();

    this.container.classList.add("open");
    this.workspace.classList.add("evidence-open");

    const hlBtn = document.getElementById("btnToggleHighlights");
    if (hlBtn) hlBtn.classList.toggle("active", state.showHighlights);
    const thumbBtn = document.getElementById("btnToggleThumbnails");
    if (thumbBtn) thumbBtn.classList.toggle("active", state.showThumbnails);

    this.renderCurrentPage();
  }

  close() {
    this.container.classList.remove("open");
    this.workspace.classList.remove("evidence-open");
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    }
  }

  renderCurrentPage() {
    const pageNum = Math.max(1, Math.min(this.totalPages, state.viewerPage));
    state.viewerPage = pageNum;

    // Verified page reference without fabricated printed-page claims
    if (this.pageIndicator) {
      this.pageIndicator.textContent = `PDF page ${pageNum} of ${this.totalPages}`;
    }
    if (this.pageJumpInput) {
      this.pageJumpInput.value = pageNum;
      this.pageJumpInput.max = this.totalPages;
    }
    if (this.docTitleEl) {
      this.docTitleEl.textContent = state.viewerDoc || this.currentDocFile;
    }

    // Set page image source
    // Uploads store compact previews for fast readiness. The full evidence
    // viewer requests a cached 300-DPI page so zooming and citation review
    // retain the previous visual fidelity.
    const imgUrl = `${this.currentDocument.pageImageBase}/page_${pageNum}.png?quality=high`;
    this.stage.hidden = true;
    if (this.pageStatus) {
      this.pageStatus.hidden = false;
      this.pageStatus.textContent = `Loading page ${pageNum}…`;
    }
    this.pageImage.alt = `PDF page ${pageNum} of ${this.currentDocument.filename}`;
    this.pageImage.dataset.fileId = this.currentDocument.fileId;
    this.pageImage.src = imgUrl;
    document.getElementById("btnPrevPage").disabled = pageNum <= 1;
    document.getElementById("btnNextPage").disabled = pageNum >= this.totalPages;

    // Update thumbnail active ring
    document.querySelectorAll(".thumbnail-item").forEach((item) => {
      const active = parseInt(item.dataset.page) === pageNum;
      item.classList.toggle("active", active);
      if (active) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });

    // Update text drawer if open
    if (state.showTextDrawer) {
      this.updateTextDrawerContent();
    }

    // Render Bounding Box Overlays
    this.renderBoundingBoxes();
    this.applyZoom();
  }

  updateTextDrawerContent() {
    if (!this.textDrawerContent) return;
    const pageNum = state.viewerPage;
    const rawText = this.currentDocument.pageText?.[pageNum];

    if (rawText) {
      this.textDrawerContent.textContent = rawText;
    } else {
      this.textDrawerContent.textContent = "Native text is not available for this page. This PDF may be scanned, or it was uploaded before text was saved.";
    }
  }

  renderBoundingBoxes() {
    this.boxLayer.replaceChildren();
    if (!state.viewerBox || !state.showHighlights) return;

    // Validate coordinate space: coordinates must be within 0..1000
    const box = state.viewerBox;
    if (
      box.ymin == null ||
      box.xmin == null ||
      box.ymax == null ||
      box.xmax == null ||
      box.ymin >= box.ymax ||
      box.xmin >= box.xmax
    ) {
      return; // Invalid coordinates; suppress highlight
    }

    const topPercent = Math.max(0, Math.min(100, (box.ymin / 1000) * 100));
    const leftPercent = Math.max(0, Math.min(100, (box.xmin / 1000) * 100));
    const heightPercent = Math.max(1, Math.min(100 - topPercent, ((box.ymax - box.ymin) / 1000) * 100));
    const widthPercent = Math.max(1, Math.min(100 - leftPercent, ((box.xmax - box.xmin) / 1000) * 100));

    const overlay = document.createElement("div");
    overlay.className = "bounding-box-overlay";
    overlay.style.top = `${topPercent}%`;
    overlay.style.left = `${leftPercent}%`;
    overlay.style.height = `${heightPercent}%`;
    overlay.style.width = `${widthPercent}%`;

    const tag = document.createElement("div");
    tag.className = "box-label-tag";
    tag.textContent = "Cited Evidence Region";
    overlay.appendChild(tag);

    this.boxLayer.appendChild(overlay);

    // Scroll into view gently
    setTimeout(() => {
      overlay.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
    }, 120);
  }

  applyZoom() {
    if (this.stage && this.viewport.clientWidth) {
      const style = getComputedStyle(this.viewport);
      const available = this.viewport.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
      // Use real layout width so both edges remain reachable by scrolling.
      this.stage.style.width = `${Math.max(1, available) * state.viewerZoom}px`;
      this.stage.style.transform = "none";
      const fit = document.getElementById("btnZoomReset");
      if (fit) fit.textContent = `${Math.round(state.viewerZoom * 100)}% · Fit`;
    }
  }

  renderThumbnails() {
    if (!this.thumbnailsPanel) return;
    this.thumbnailsPanel.replaceChildren();

    for (let p = 1; p <= this.totalPages; p++) {
      const item = document.createElement("button");
      item.type = "button";
      item.setAttribute("aria-label", `Open PDF page ${p}`);
      item.className = `thumbnail-item ${p === state.viewerPage ? "active" : ""}`;
      item.dataset.page = p;

      const img = document.createElement("img");
      img.className = "thumbnail-img";
      img.src = `${this.currentDocument.pageImageBase}/page_${p}.png`;
      img.alt = `Thumbnail PDF page ${p}`;
      img.loading = "lazy";

      const label = document.createElement("span");
      label.className = "thumbnail-label";
      label.textContent = `Page ${p}`;

      item.appendChild(img);
      item.appendChild(label);

      item.addEventListener("click", () => {
        state.setViewerPage(p);
      });

      this.thumbnailsPanel.appendChild(item);
    }
  }

  initDividerDrag() {
    if (!this.divider) return;
    let isDragging = false;

    this.divider.addEventListener("mousedown", () => {
      isDragging = true;
      this.divider.classList.add("active");
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    });

    document.addEventListener("mousemove", (e) => {
      if (!isDragging || !this.workspace) return;
      const workspaceRect = this.workspace.getBoundingClientRect();
      const newWidth = workspaceRect.right - e.clientX;
      const percent = (newWidth / workspaceRect.width) * 100;

      // Restrain between 30% and 65% with min width 360px
      if (percent >= 28 && percent <= 65 && newWidth >= 360 && workspaceRect.width - newWidth >= 488) {
        this.container.style.width = `${percent}%`;
      }
    });

    document.addEventListener("mouseup", () => {
      if (isDragging) {
        isDragging = false;
        this.divider.classList.remove("active");
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      }
    });
  }

  initKeyboardShortcuts() {
    document.addEventListener("keydown", (e) => {
      if (!state.isViewerOpen || state.activeModal) return;
      if (e.key === "Escape") {
        state.closeEvidence();
      } else if (e.key === "ArrowLeft" && !e.target.matches("input, textarea")) {
        state.setViewerPage(state.viewerPage - 1);
      } else if (e.key === "ArrowRight" && !e.target.matches("input, textarea")) {
        state.setViewerPage(state.viewerPage + 1);
      }
    });
  }
}
