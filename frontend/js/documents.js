/* ==========================================================================
   EVID DOCUMENTS LIBRARY CONTROLLER
   - Accurate search, combined filters (type & status), visible counts
   - Clear filters action and helpful empty states
   - Empty project onboarding: "Your documents start here"
   - Replaces "Review Boundaries" with "Review document sections"
   - Preserves original files as parents with expandable sections
   - Safe DOM rendering via textContent / DOM APIs
   ========================================================================== */

class DocumentsController {
  constructor() {
    this.tableBody = document.getElementById("docsTableBody");
    this.searchInput = document.getElementById("docSearchInput");
    this.typeFilter = document.getElementById("docTypeFilter");
    this.statusFilter = document.getElementById("docStatusFilter");
    this.btnClearFilters = document.getElementById("btnClearDocFilters");
    this.resultsCountLabel = document.getElementById("docsCountLabel");
    this.emptyStateContainer = document.getElementById("docsEmptyState");

    // Modal elements
    this.boundaryModalOverlay = document.getElementById("boundaryModalOverlay");
    this.boundaryModalTitle = document.getElementById("boundarySubdocTitle");
    this.boundaryTitleInput = document.getElementById("boundaryEditTitle");
    this.boundaryTypeSelect = document.getElementById("boundaryEditType");
    this.boundaryStartPage = document.getElementById("boundaryEditStartPage");
    this.boundaryEndPage = document.getElementById("boundaryEditEndPage");
    this.boundaryIdentifiersList = document.getElementById("boundaryIdentifiersList");

    this.initEvents();
    this.render();

    state.subscribe((event) => {
      const loadStatus = document.getElementById("libraryLoadStatus");
      if (loadStatus && ["library_loading", "library_loaded", "library_load_error"].includes(event)) {
        loadStatus.hidden = event === "library_loaded";
        loadStatus.textContent = event === "library_loading" ? "Loading saved source files…" : event === "library_load_error" ? "Saved source files could not be loaded. Check the CiteCanvas server, then refresh this page." : "";
      }
      if (["subdoc_updated", "doc_search_changed", "document_added"].includes(event)) {
        this.render();
      } else if (event === "boundary_modal_open") {
        this.openSectionModal();
      } else if (event === "boundary_modal_close") {
        if (this.boundaryModalOverlay) this.boundaryModalOverlay.classList.remove("open");
      }
    });
  }

  initEvents() {
    if (this.searchInput) {
      this.searchInput.addEventListener("input", (e) => {
        state.docSearchQuery = e.target.value.toLowerCase().trim();
        this.render();
      });
    }

    if (this.typeFilter) {
      this.typeFilter.addEventListener("change", (e) => {
        state.docTypeFilter = e.target.value;
        this.render();
      });
    }

    if (this.statusFilter) {
      this.statusFilter.addEventListener("change", (e) => {
        state.docStatusFilter = e.target.value;
        this.render();
      });
    }

    if (this.btnClearFilters) {
      this.btnClearFilters.addEventListener("click", () => {
        this.clearFilters();
      });
    }

    // Boundary / Section Modal Actions
    const btnCancel = document.getElementById("btnCancelBoundary");
    if (btnCancel) {
      btnCancel.addEventListener("click", () => state.closeBoundaryReview());
    }

    const btnSave = document.getElementById("btnSaveBoundary");
    if (btnSave) {
      btnSave.addEventListener("click", () => {
        if (!state.editingSubdoc) return;
        state.editingSubdoc.title = this.boundaryTitleInput.value.trim() || state.editingSubdoc.title;
        state.editingSubdoc.docType = this.boundaryTypeSelect.value;
        state.editingSubdoc.startPage = parseInt(this.boundaryStartPage.value, 10) || state.editingSubdoc.startPage;
        state.editingSubdoc.endPage = parseInt(this.boundaryEndPage.value, 10) || state.editingSubdoc.endPage;
        const owner = state.getDocuments().find(file => file.subdocuments.some(section => section.subdocId === state.editingSubdoc.subdocId));
        const total = owner?.totalPages || 1;
        state.editingSubdoc.startPage = Math.max(1, Math.min(total, state.editingSubdoc.startPage));
        state.editingSubdoc.endPage = Math.max(state.editingSubdoc.startPage, Math.min(total, state.editingSubdoc.endPage));
        state.editingSubdoc.pageCount = state.editingSubdoc.endPage - state.editingSubdoc.startPage + 1;
        state.saveBoundaryReview(state.editingSubdoc);
      });
    }

    const btnReset = document.getElementById("btnResetBoundary");
    if (btnReset) {
      btnReset.addEventListener("click", () => {
        if (!state.editingSubdoc) return;
        const owner = state.getDocuments().find(file => file.subdocuments.some(s => s.subdocId === state.editingSubdoc.subdocId));
        const orig = (owner?.isSample ? PHARMA_SAMPLE_PROJECT.subdocuments : owner?.importedSections || []).find(s => s.subdocId === state.editingSubdoc.subdocId);
        if (orig) {
          state.openBoundaryReview(orig);
        }
      });
    }
  }

  clearFilters() {
    state.docSearchQuery = "";
    state.docTypeFilter = "all";
    state.docStatusFilter = "all";
    if (this.searchInput) this.searchInput.value = "";
    if (this.typeFilter) this.typeFilter.value = "all";
    if (this.statusFilter) this.statusFilter.value = "all";
    this.render();
  }

  render() {
    if (!this.tableBody) return;
    this.tableBody.replaceChildren();

    const documents = state.getDocuments();
    const subdocs = documents.flatMap(file => file.subdocuments || []);
    const fileCount = documents.length;
    const overview = {
      libraryFileCount: fileCount,
      librarySectionCount: subdocs.length,
      libraryReviewCount: subdocs.filter(doc => doc.metadataStatus !== "User-confirmed").length,
      topbarDocBadge: fileCount,
    };
    Object.entries(overview).forEach(([id, value]) => {
      const element = document.getElementById(id);
      if (element) element.textContent = value;
    });
    document.getElementById("viewDocuments").classList.toggle("is-empty", fileCount === 0);
    if (this.emptyStateContainer) this.emptyStateContainer.hidden = fileCount !== 0;
    document.getElementById("topbarDocBadge").hidden = fileCount === 0;
    const sampleNote = document.getElementById("librarySampleNote");
    if (sampleNote) sampleNote.hidden = !state.project.isSampleProject;

    // Filter subdocuments
    const filteredSubdocs = subdocs.filter((sd) => {
      const q = state.docSearchQuery;
      const matchesSearch =
        !q ||
        sd.title.toLowerCase().includes(q) ||
        documents.find(file => file.subdocuments.includes(sd))?.filename.toLowerCase().includes(q) ||
        Object.values(sd.scopedIdentifiers || {}).some((v) => String(v).toLowerCase().includes(q));

      const matchesType =
        state.docTypeFilter === "all" ||
        sd.docType.toLowerCase() === state.docTypeFilter.toLowerCase();

      let matchesStatus = true;
      if (state.docStatusFilter === "confirmed") {
        matchesStatus = sd.metadataStatus === "User-confirmed";
      } else if (state.docStatusFilter === "suggested") {
        matchesStatus = sd.metadataStatus === "Suggested (AI)";
      } else if (state.docStatusFilter === "imported") {
        matchesStatus = sd.metadataStatus === "User-uploaded";
      }

      return matchesSearch && matchesType && matchesStatus;
    });

    const hasActiveFilters = Boolean(
      state.docSearchQuery || state.docTypeFilter !== "all" || state.docStatusFilter !== "all"
    );

    if (this.btnClearFilters) {
      this.btnClearFilters.style.display = hasActiveFilters ? "inline-flex" : "none";
    }

    // Update count label
    if (this.resultsCountLabel) {
      if (hasActiveFilters) {
        this.resultsCountLabel.textContent = `Showing ${filteredSubdocs.length} of ${subdocs.length} document sections`;
      } else {
        this.resultsCountLabel.textContent = `${subdocs.length} document sections in ${fileCount} source ${fileCount === 1 ? "file" : "files"}`;
      }
    }

    // Handle No Results State
    if (fileCount === 0) {
      return;
    }

    if (filteredSubdocs.length === 0) {
      const trEmpty = document.createElement("tr");
      const tdEmpty = document.createElement("td");
      tdEmpty.colSpan = 6;
      tdEmpty.style.textAlign = "center";
      tdEmpty.style.padding = "48px 24px";
      tdEmpty.style.color = "var(--color-text-secondary)";

      const emptyTitle = document.createElement("div");
      emptyTitle.style.fontWeight = "600";
      emptyTitle.style.fontSize = "15px";
      emptyTitle.style.color = "var(--color-text-primary)";
      emptyTitle.style.marginBottom = "6px";
      emptyTitle.textContent = "No document sections match your filters.";
      tdEmpty.appendChild(emptyTitle);

      const emptyBtn = document.createElement("button");
      emptyBtn.className = "btn btn-secondary btn-sm";
      emptyBtn.textContent = "Clear filters";
      emptyBtn.style.marginTop = "8px";
      emptyBtn.addEventListener("click", () => this.clearFilters());
      tdEmpty.appendChild(emptyBtn);

      trEmpty.appendChild(tdEmpty);
      this.tableBody.appendChild(trEmpty);
      return;
    }

    documents.forEach(master => {
    const matchingSections = filteredSubdocs.filter(section => master.subdocuments.includes(section));
    if (hasActiveFilters && matchingSections.length === 0) return;

    // Each original file owns only its own section rows.
    const isExpanded = state.expandedBundles.has(master.fileId);
    const parentTr = document.createElement("tr");
    parentTr.className = `parent-row ${isExpanded ? "expanded" : ""}`;
    parentTr.dataset.fileId = master.fileId;

    // Col 1: Expand chevron, icon, filename, count badge
    const tdName = document.createElement("td");
    const parentName = document.createElement("div");
    parentName.className = "document-name-content";

    const chevron = document.createElement("button");
    chevron.className = "expand-chevron";
    chevron.type = "button";
    chevron.setAttribute("aria-label", `${isExpanded ? "Collapse" : "Expand"} sections in ${master.filename}`);
    chevron.setAttribute("aria-expanded", String(isExpanded));
    chevron.addEventListener("click", () => this.toggleParent(master.fileId));
    chevron.textContent = isExpanded ? "▼" : "▶";
    chevron.style.fontSize = "11px";
    chevron.style.cursor = "pointer";
    parentName.appendChild(chevron);

    const pdfSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    pdfSvg.setAttribute("width", "18");
    pdfSvg.setAttribute("height", "18");
    pdfSvg.setAttribute("viewBox", "0 0 24 24");
    pdfSvg.setAttribute("fill", "none");
    pdfSvg.setAttribute("stroke", "currentColor");
    pdfSvg.setAttribute("stroke-width", "2");
    pdfSvg.style.color = "var(--color-primary)";

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z");
    const poly = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    poly.setAttribute("points", "14 2 14 8 20 8");
    pdfSvg.appendChild(path);
    pdfSvg.appendChild(poly);
    parentName.appendChild(pdfSvg);

    const nameStrong = document.createElement("strong");
    nameStrong.style.color = "var(--color-text-primary)";
    nameStrong.textContent = master.filename;
    parentName.appendChild(nameStrong);

    const countBadge = document.createElement("span");
    countBadge.className = "subdoc-count-badge";
    countBadge.textContent = `${master.subdocuments.length} ${master.subdocuments.length === 1 ? "section" : "sections"}`;
    parentName.appendChild(countBadge);
    tdName.appendChild(parentName);
    parentTr.appendChild(tdName);

    // Col 2: Type
    const tdType = document.createElement("td");
    const typeBadge = document.createElement("span");
    typeBadge.className = "badge badge-neutral";
    typeBadge.textContent = master.isSample ? "Sample PDF" : "Original PDF";
    tdType.appendChild(typeBadge);
    parentTr.appendChild(tdType);

    // Col 3: Pages
    const tdPages = document.createElement("td");
    tdPages.textContent = `${master.totalPages} pages`;
    parentTr.appendChild(tdPages);

    // Col 4: Status
    const tdStatus = document.createElement("td");
    const statusBadge = document.createElement("span");
    statusBadge.className = "badge badge-success";
    statusBadge.textContent = "✓ Ready";
    tdStatus.appendChild(statusBadge);
    parentTr.appendChild(tdStatus);

    // Col 5: Added
    const tdAdded = document.createElement("td");
    tdAdded.textContent = this.formatUploadDate(master.uploadedAt);
    parentTr.appendChild(tdAdded);

    // Col 6: Actions
    const tdActions = document.createElement("td");
    const openBtn = document.createElement("button");
    openBtn.className = "btn btn-secondary btn-sm";
    openBtn.textContent = "Open";
    openBtn.title = "Open parent PDF in Evidence Viewer";
    openBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      state.openEvidence(1, null, master.filename, openBtn, master.fileId);
    });
    tdActions.appendChild(openBtn);
    parentTr.appendChild(tdActions);

    parentTr.addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      this.toggleParent(master.fileId);
    });

    this.tableBody.appendChild(parentTr);

    // 2. Render Nested Sub-Document Rows if expanded
    if (isExpanded) {
      matchingSections.forEach((sd) => {
        const subTr = document.createElement("tr");
        subTr.className = "subdoc-row";
        subTr.dataset.fileId = master.fileId;
        subTr.dataset.sectionId = sd.subdocId;

        // Col 1: Title and scoped identifiers
        const tdSubTitle = document.createElement("td");
        tdSubTitle.className = "subdoc-title-cell";
        const titleContent = document.createElement("div");
        titleContent.className = "document-name-content";

        const treeIcon = document.createElement("span");
        treeIcon.className = "subdoc-tree-icon";
        treeIcon.setAttribute("aria-hidden", "true");
        treeIcon.textContent = "↳";
        titleContent.appendChild(treeIcon);

        const titleCol = document.createElement("div");
        titleCol.style.display = "flex";
        titleCol.style.flexDirection = "column";

        const titleSpan = document.createElement("span");
        titleSpan.style.fontWeight = "500";
        titleSpan.style.color = "var(--color-text-primary)";
        titleSpan.textContent = sd.title;
        titleCol.appendChild(titleSpan);

        const idStrings = Object.entries(sd.scopedIdentifiers || {})
          .map(([key, value]) => {
            const label = key.replace(/([a-z])([A-Z])/g, "$1 $2");
            return `${label.charAt(0).toUpperCase() + label.slice(1)}: ${value}`;
          })
          .join(" · ");

        if (idStrings) {
          const idSpan = document.createElement("span");
          idSpan.className = "document-identifiers";
          idSpan.textContent = idStrings;
          idSpan.title = idStrings;
          titleCol.appendChild(idSpan);
        }

        titleContent.appendChild(titleCol);
        tdSubTitle.appendChild(titleContent);
        subTr.appendChild(tdSubTitle);

        // Col 2: Doc Type
        const tdSubType = document.createElement("td");
        const subTypeBadge = document.createElement("span");
        subTypeBadge.className = "badge badge-info";
        subTypeBadge.textContent = sd.docType;
        tdSubType.appendChild(subTypeBadge);
        subTr.appendChild(tdSubType);

        // Col 3: Pages
        const tdSubPages = document.createElement("td");
        tdSubPages.textContent =
          sd.startPage === sd.endPage ? `Page ${sd.startPage}` : `Pages ${sd.startPage}–${sd.endPage}`;
        subTr.appendChild(tdSubPages);

        // Col 4: Metadata Status
        const tdSubStatus = document.createElement("td");
        const isConfirmed = sd.metadataStatus === "User-confirmed";
        const metaStatus = document.createElement("span");
        metaStatus.className = `badge ${isConfirmed ? "badge-success" : "badge-neutral"}`;
        metaStatus.textContent = isConfirmed ? "✓ User-confirmed" : master.isSample ? "Suggested (AI)" : "Imported";
        tdSubStatus.appendChild(metaStatus);
        subTr.appendChild(tdSubStatus);

        // Col 5: Date
        const tdSubDate = document.createElement("td");
        tdSubDate.textContent = this.formatUploadDate(master.uploadedAt);
        subTr.appendChild(tdSubDate);

        // Col 6: Actions
        const tdSubActions = document.createElement("td");
        const btnGroup = document.createElement("div");
        btnGroup.style.display = "flex";
        btnGroup.style.gap = "6px";

        const viewSubBtn = document.createElement("button");
        viewSubBtn.className = "btn btn-secondary btn-sm";
        viewSubBtn.textContent = "View";
        viewSubBtn.title = "View in Evidence Viewer";
        viewSubBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          state.openEvidence(sd.startPage, null, `${sd.title} (${master.filename})`, viewSubBtn, master.fileId);
        });
        btnGroup.appendChild(viewSubBtn);

        // Renamed from "Review Boundaries" to "Review document sections"
        const reviewSubBtn = document.createElement("button");
        reviewSubBtn.className = "btn btn-subtle btn-sm";
        reviewSubBtn.textContent = "Review section";
        reviewSubBtn.setAttribute("aria-label", `Review document sections: ${sd.title}`);
        reviewSubBtn.title = "Review or edit document section boundary";
        reviewSubBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          state.openBoundaryReview(sd);
        });
        btnGroup.appendChild(reviewSubBtn);

        tdSubActions.appendChild(btnGroup);
        subTr.appendChild(tdSubActions);

        this.tableBody.appendChild(subTr);
      });
    }
    });
  }

  formatUploadDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? (value || "Today") : date.toLocaleDateString(undefined, {month: "short", day: "numeric", year: "numeric"});
  }

  toggleParent(fileId) {
    if (state.expandedBundles.has(fileId)) {
      state.expandedBundles.delete(fileId);
    } else {
      state.expandedBundles.add(fileId);
    }
    this.render();
  }

  openSectionModal() {
    const sd = state.editingSubdoc;
    if (!sd || !this.boundaryModalOverlay) return;
    this.boundaryModalTitle.textContent = `Review document sections: ${sd.title}`;
    this.boundaryTitleInput.value = sd.title;
    this.boundaryTypeSelect.value = sd.docType;
    const owner = state.getDocuments().find(file => file.subdocuments.some(section => section.subdocId === sd.subdocId));
    this.boundaryStartPage.max = owner?.totalPages || 1;
    this.boundaryEndPage.max = owner?.totalPages || 1;
    this.boundaryStartPage.value = sd.startPage;
    this.boundaryEndPage.value = sd.endPage;

    if (this.boundaryIdentifiersList) {
      this.boundaryIdentifiersList.replaceChildren();
      Object.entries(sd.scopedIdentifiers || {}).forEach(([k, v]) => {
        const li = document.createElement("li");
        const strong = document.createElement("strong");
        strong.textContent = `${k}: `;
        li.appendChild(strong);
        li.appendChild(document.createTextNode(String(v)));
        this.boundaryIdentifiersList.appendChild(li);
      });
    }

    this.boundaryModalOverlay.classList.add("open");
  }
}
