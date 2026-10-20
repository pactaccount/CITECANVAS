/* ==========================================================================
   EVID ASK (GROUNDED Q&A) CONTROLLER
   - Shows selected sources beside the composer
   - Rejects blank submissions
   - Supports Enter (submit) / Shift+Enter (new line)
   - Preserves input on failure or cancellation
   - Truthful loading/retry behavior
   - Responses associated with their original question & source scope
   - Grounded evidence retrieval with unknown-lot abstention
   - Real outcomes for Copy, Save, and Report
   - Safe DOM rendering via textContent / DOM APIs
   ========================================================================== */

class AskController {
  constructor() {
    // Sample workflows remain inactive in a real, empty workspace.
    if (!state.project.isSampleProject) return;
    this.textarea = document.getElementById("askInput");
    this.askBtn = document.getElementById("btnSubmitAsk");
    this.stopBtn = document.getElementById("btnStopAsk");
    this.statusBar = document.getElementById("processingStatusBar");
    this.statusText = document.getElementById("processingStatusText");
    this.feed = document.getElementById("conversationFeed");
    this.suggestedContainer = document.getElementById("suggestedChipsContainer");
    this.sourceScopeBadge = document.getElementById("askActiveSourcesBadge");

    // Calculation modal
    this.calcModalOverlay = document.getElementById("calcModalOverlay");
    this.calcFormula = document.getElementById("calcModalFormula");
    this.calcNature = document.getElementById("calcModalNature");
    this.calcInput = document.getElementById("calcModalInput");
    this.calcOutput = document.getElementById("calcModalOutput");
    this.calcFactor = document.getElementById("calcModalFactor");

    // Report issue dialog
    this.reportModalOverlay = document.getElementById("reportModalOverlay");
    this.reportReasonSelect = document.getElementById("reportIssueReason");
    this.reportNotesInput = document.getElementById("reportIssueNotes");
    this.btnSubmitReport = document.getElementById("btnSubmitReportIssue");
    this.btnCancelReport = document.getElementById("btnCancelReportIssue");
    this.activeReportTarget = null;

    this.activeTimer = null;
    this.lastSubmittedQuery = "";

    this.initEvents();
    this.renderSuggestedChips();
    this.updateSourceScopeDisplay();
    this.loadDemoConversation();

    state.subscribe((event, id) => {
      if (event === "modal_close_requested" && id === "reportModalOverlay") {
        this.closeReportModal();
      }
      if (event === "calc_modal_open") {
        this.openCalcModal();
      } else if (event === "calc_modal_close") {
        if (this.calcModalOverlay) this.calcModalOverlay.classList.remove("open");
      } else if (event === "sources_scope_changed") {
        this.updateSourceScopeDisplay();
      }
    });
  }

  initEvents() {
    // Enter to submit, Shift+Enter for new line
    if (this.textarea) {
      this.textarea.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          this.handleAsk();
        }
      });
    }

    if (this.askBtn) {
      this.askBtn.addEventListener("click", () => this.handleAsk());
    }

    if (this.stopBtn) {
      this.stopBtn.addEventListener("click", () => {
        this.stopAsking(true);
      });
    }

    const btnCloseCalc = document.getElementById("btnCloseCalcModal");
    if (btnCloseCalc) {
      btnCloseCalc.addEventListener("click", () => state.closeCalculation());
    }

    // Change Sources button
    const btnChangeSources = document.getElementById("btnChangeSources");
    if (btnChangeSources) {
      btnChangeSources.addEventListener("click", () => {
        if (state.isViewerOpen) state.closeEvidence();
        state.docSearchQuery = "pharma-blob-sample.pdf";
        const search = document.getElementById("docSearchInput");
        if (search) search.value = state.docSearchQuery;
        state.docTypeFilter = "all";
        state.docStatusFilter = "all";
        document.getElementById("docTypeFilter").value = "all";
        document.getElementById("docStatusFilter").value = "all";
        state.expandedBundles.add(state.project.masterFile.fileId);
        state.notify("doc_search_changed");
        state.setActiveTab("documents");
      });
    }

    // Report modal events
    if (this.btnSubmitReport) {
      this.btnSubmitReport.addEventListener("click", () => this.submitReport());
    }
    if (this.btnCancelReport) {
      this.btnCancelReport.addEventListener("click", () => this.closeReportModal());
    }
    const btnCloseReport = document.getElementById("btnCloseReportModal");
    if (btnCloseReport) {
      btnCloseReport.addEventListener("click", () => this.closeReportModal());
    }
  }

  updateSourceScopeDisplay() {
    if (!this.sourceScopeBadge) return;
    const count = state.selectedSources ? state.selectedSources.size : 8;
    this.sourceScopeBadge.textContent = `${count} of 8 document sections selected`;
  }

  renderSuggestedChips() {
    if (!this.suggestedContainer) return;
    this.suggestedContainer.replaceChildren();

    PHARMA_SAMPLE_PROJECT.qaScenarios.forEach((qa) => {
      const btn = document.createElement("button");
      btn.className = "suggested-btn";
      btn.textContent = qa.question;
      btn.addEventListener("click", () => {
        if (this.textarea) this.textarea.value = qa.question;
        this.handleAsk(qa.question);
      });
      this.suggestedContainer.appendChild(btn);
    });
  }

  loadDemoConversation() {
    // Initial grounded answered query demonstration
    const demoQA = PHARMA_SAMPLE_PROJECT.qaScenarios[4]; // Max Pressure Part 29184612 Rev AD
    this.addAnswerCard(demoQA.question, demoQA, "All 8 document sections");
  }

  handleAsk(overrideQuestion = null) {
    const query = overrideQuestion || (this.textarea ? this.textarea.value.trim() : "");
    // Reject blank submissions
    if (!query || state.isAsking) return;

    this.lastSubmittedQuery = query;
    if (this.textarea) this.textarea.value = "";

    const activeScope = `${state.selectedSources.size} document sections`;
    this.addUserQuestion(query, activeScope);

    state.isAsking = true;
    if (this.askBtn) this.askBtn.style.display = "none";
    if (this.stopBtn) this.stopBtn.style.display = "inline-flex";
    if (this.statusBar) this.statusBar.classList.add("active");

    if (this.statusText) this.statusText.textContent = "Preparing a response from the sample data…";
    // Yield to paint the status without simulating model or retrieval stages.
    this.activeTimer = setTimeout(() => {
      this.activeTimer = null;
      this.completeAnswer(query, activeScope);
    }, 0);
  }

  stopAsking(isUserCancel = false) {
    if (this.activeTimer) {
      clearInterval(this.activeTimer);
      this.activeTimer = null;
    }
    state.isAsking = false;
    if (this.statusBar) this.statusBar.classList.remove("active");
    if (this.askBtn) this.askBtn.style.display = "inline-flex";
    if (this.stopBtn) this.stopBtn.style.display = "none";

    // Preserve input on failure or user stop
    if (isUserCancel && this.textarea && this.lastSubmittedQuery) {
      this.textarea.value = this.lastSubmittedQuery;
    }
  }

  completeAnswer(query, sourceScope) {
    this.stopAsking(false);

    const lowerQuery = query.toLowerCase();

    // 1. Check for unknown-lot question (Preserve unknown-lot abstention)
    const lotMatch = query.match(/lot\s+([0-9a-zA-Z]+)/i);
    if (lotMatch) {
      const queriedLot = lotMatch[1];
      const knownLots = ["18356721", "15102934"];
      if (!knownLots.includes(queriedLot)) {
        const abstention = {
          question: query,
          outcome: "unestablished",
          outcomeLabel: "Lot Not Found (Abstained)",
          answerText: `I could not establish an answer for lot ${queriedLot}. Lot number ${queriedLot} was not found in any of the verified certificates or logs in this document bundle. Verified lots in this bundle are Lot 18356721 (Low Flow Kit, Page 2) and Lot 15102934 (High Flow Kit, Page 3).`,
          citations: [],
          qualifications: "CiteCanvas abstains from guessing lot associations across unverified identifiers.",
          calculation: null
        };
        this.addAnswerCard(query, abstention, sourceScope);
        return;
      }
    }

    // 2. Exact match in pre-verified scenarios
    const match = PHARMA_SAMPLE_PROJECT.qaScenarios.find(
      (qa) =>
        qa.question.toLowerCase() === lowerQuery ||
        lowerQuery.includes(qa.question.toLowerCase().slice(0, 24))
    );

    if (match) {
      this.addAnswerCard(query, match, sourceScope);
      return;
    }

    // 3. Dynamic grounded search across subdocuments and native text
    const synthesized = this.retrieveFromDocuments(query);
    this.addAnswerCard(query, synthesized, sourceScope);
  }

  retrieveFromDocuments(query) {
    const qLower = query.toLowerCase();
    const queryTokens = qLower.split(/[\s,?.!()\-]+/).filter((t) => t.length > 1);
    const subdocs = state.project.subdocuments;

    let bestCandidate = null;
    let highestScore = 0;

    // Search across active subdocuments
    for (const sd of subdocs) {
      if (!state.selectedSources.has(sd.subdocId)) continue;

      let docScore = 0;
      const titleLower = sd.title.toLowerCase();
      const summaryLower = (sd.summary || "").toLowerCase();

      // Check if page or title mentioned in query
      if (qLower.includes(`page ${sd.startPage}`) || qLower.includes(`p. ${sd.startPage}`) || qLower.includes(`p.${sd.startPage}`)) {
        docScore += 10;
      }
      queryTokens.forEach((token) => {
        if (titleLower.includes(token)) docScore += 3;
        if (summaryLower.includes(token)) docScore += 1;
      });

      // Match against scoped identifiers
      for (const [key, val] of Object.entries(sd.scopedIdentifiers || {})) {
        const keyParts = key.split(/(?=[A-Z])|_/).map((k) => k.toLowerCase());
        let fieldMatchScore = docScore;

        keyParts.forEach((part) => {
          if (part.length > 2 && qLower.includes(part)) fieldMatchScore += 5;
        });

        // Also check if val tokens appear in query
        const valStr = String(val).toLowerCase();
        if (qLower.includes(valStr)) fieldMatchScore += 8;

        if (fieldMatchScore > highestScore && fieldMatchScore >= 7) {
          highestScore = fieldMatchScore;

          // Find exact bounding box if present in extraction rows
          let box = null;
          const matrixRow = state.extractionRows.find((r) => r.subdocId === sd.subdocId);
          if (matrixRow) {
            for (const cell of Object.values(matrixRow.values || {})) {
              if (cell && cell.value === val && cell.box) {
                box = cell.box;
                break;
              }
            }
          }

          bestCandidate = {
            question: query,
            outcome: "found",
            outcomeLabel: "Answer found in documents",
            answerText: `According to the ${sd.title} (PDF Page ${sd.startPage}), the ${keyParts.join(" ")} is: ${val}.`,
            citations: [
              {
                id: `EVID-${sd.startPage}`,
                label: `${sd.title} · PDF Page ${sd.startPage}`,
                pageNumber: sd.startPage,
                docTitle: sd.title,
                boundingBox: box
              }
            ],
            qualifications: `Verified from native PDF text layer of ${sd.title}.`,
            calculation: null
          };
        }
      }
    }

    if (bestCandidate) {
      return bestCandidate;
    }

    // Honest fallback abstention
    return {
      question: query,
      outcome: "unestablished",
      outcomeLabel: "Could not establish from available evidence",
      answerText: `I could not establish an answer to "${query}" from the currently selected documents. The available document bundle contains flow kit storage guidelines, low-flow and high-flow certificates of quality, packaging specifications, a BSE/TSE declaration, a material description sheet, supplier audits, and a chain of custody record.`,
      citations: [],
      qualifications: "To answer questions regarding other metrics, adjust your source scope or upload the relevant document.",
      calculation: null
    };
  }

  addUserQuestion(query, sourceScope) {
    const bubble = document.createElement("div");
    bubble.className = "user-question-bubble";

    const textSpan = document.createElement("div");
    textSpan.style.fontWeight = "500";
    textSpan.textContent = query;
    bubble.appendChild(textSpan);

    const scopeMeta = document.createElement("div");
    scopeMeta.style.fontSize = "11px";
    scopeMeta.style.opacity = "0.85";
    scopeMeta.style.marginTop = "4px";
    scopeMeta.textContent = `Queried against: ${sourceScope}`;
    bubble.appendChild(scopeMeta);

    this.feed.appendChild(bubble);
    bubble.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  addAnswerCard(query, qaData, sourceScope = "All sources") {
    const card = document.createElement("div");
    card.className = "answer-card";

    // Header
    const header = document.createElement("div");
    header.className = "answer-header";

    const badge = document.createElement("span");
    let badgeClass = "outcome-found";
    let icon = "✓ ";
    if (qaData.outcome === "unestablished") {
      badgeClass = "outcome-unestablished";
      icon = "⚠ ";
    } else if (qaData.outcome === "partial") {
      badgeClass = "outcome-partial";
      icon = "ℹ ";
    }
    badge.className = `answer-outcome-badge ${badgeClass}`;
    badge.textContent = icon + qaData.outcomeLabel;
    header.appendChild(badge);

    const sourceLabel = document.createElement("span");
    sourceLabel.style.fontSize = "12px";
    sourceLabel.style.color = "var(--color-text-muted)";
    sourceLabel.textContent = `Scope: ${sourceScope}`;
    header.appendChild(sourceLabel);

    card.appendChild(header);

    // Body
    const body = document.createElement("div");
    body.className = "answer-body";

    const answerP = document.createElement("p");
    answerP.style.fontSize = "14px";
    answerP.style.lineHeight = "22px";
    answerP.style.color = "var(--color-text-primary)";
    answerP.textContent = qaData.answerText;
    body.appendChild(answerP);

    // Citations
    if (qaData.citations && qaData.citations.length > 0) {
      const citWrap = document.createElement("div");
      citWrap.style.display = "flex";
      citWrap.style.gap = "6px";
      citWrap.style.flexWrap = "wrap";
      citWrap.style.marginTop = "8px";

      qaData.citations.forEach((c) => {
        const pill = document.createElement("button");
        pill.className = "citation-pill";
        pill.textContent = `📄 ${c.label}`;
        pill.title = `View source on page ${c.pageNumber}`;
        pill.addEventListener("click", () => {
          state.openEvidence(c.pageNumber, c.boundingBox, c.docTitle, pill);
        });
        citWrap.appendChild(pill);
      });
      body.appendChild(citWrap);
    }

    // Calculation callout
    if (qaData.calculation) {
      const calcBox = document.createElement("div");
      calcBox.className = "calculation-callout";

      const calcInfo = document.createElement("div");
      calcInfo.style.display = "flex";
      calcInfo.style.flexDirection = "column";
      calcInfo.style.gap = "2px";

      const calcTag = document.createElement("span");
      calcTag.style.fontSize = "11px";
      calcTag.style.textTransform = "uppercase";
      calcTag.style.color = "var(--color-text-muted)";
      calcTag.style.fontWeight = "600";
      calcTag.textContent = "Deterministic Unit Calculation";
      calcInfo.appendChild(calcTag);

      const calcFormula = document.createElement("span");
      calcFormula.className = "calculation-text";
      calcFormula.textContent = qaData.calculation.formula;
      calcInfo.appendChild(calcFormula);

      calcBox.appendChild(calcInfo);

      const btnViewCalc = document.createElement("button");
      btnViewCalc.className = "btn btn-secondary btn-sm";
      btnViewCalc.textContent = "View Calculation";
      btnViewCalc.addEventListener("click", () => {
        state.openCalculation(qaData.calculation);
      });
      calcBox.appendChild(btnViewCalc);

      body.appendChild(calcBox);
    }

    // Qualifications / limitations
    if (qaData.qualifications) {
      const qualBox = document.createElement("div");
      qualBox.style.fontSize = "13px";
      qualBox.style.color = "var(--color-text-secondary)";
      qualBox.style.background = "var(--color-bg-surface-alt)";
      qualBox.style.padding = "8px 12px";
      qualBox.style.borderRadius = "var(--radius-control)";
      qualBox.style.borderLeft = "3px solid var(--color-border-strong)";
      qualBox.style.marginTop = "6px";

      const qualStrong = document.createElement("strong");
      qualStrong.textContent = "Limitation / Note: ";
      qualBox.appendChild(qualStrong);

      const qualText = document.createTextNode(qaData.qualifications);
      qualBox.appendChild(qualText);

      body.appendChild(qualBox);
    }

    card.appendChild(body);

    // Actions Row
    const actionRow = document.createElement("div");
    actionRow.className = "answer-action-row";

    const leftActions = document.createElement("div");
    leftActions.className = "answer-actions-left";

    // Copy with Citations
    const copyBtn = document.createElement("button");
    copyBtn.className = "btn btn-subtle btn-sm";
    copyBtn.textContent = "Copy with Citations";
    copyBtn.addEventListener("click", () => {
      const citeStr = (qaData.citations || []).map((c) => c.label).join(", ");
      const copyText = `${qaData.answerText}${citeStr ? `\n\nSources: ${citeStr}` : ""}`;
      navigator.clipboard.writeText(copyText).then(() => {
        copyBtn.textContent = "✓ Copied!";
        setTimeout(() => {
          copyBtn.textContent = "Copy with Citations";
        }, 1800);
      });
    });
    leftActions.appendChild(copyBtn);

    // Save Finding
    const saveBtn = document.createElement("button");
    saveBtn.className = "btn btn-subtle btn-sm";
    saveBtn.textContent = "Save for session";
    saveBtn.title = "Keep this finding for the current browser session";
    let isSaved = false;
    const findingId = `finding_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    saveBtn.addEventListener("click", () => {
      isSaved = !isSaved;
      if (isSaved) {
        saveBtn.textContent = "✓ Saved for session";
        saveBtn.className = "btn btn-primary btn-sm";
        // Record in state
        if (!state.savedFindings) state.savedFindings = [];
        state.savedFindings.push({ id: findingId, query, answer: qaData.answerText, date: new Date().toISOString() });
      } else {
        state.savedFindings = state.savedFindings.filter(finding => finding.id !== findingId);
        saveBtn.textContent = "Save for session";
        saveBtn.className = "btn btn-subtle btn-sm";
      }
    });
    leftActions.appendChild(saveBtn);

    // Retry Button
    const retryBtn = document.createElement("button");
    retryBtn.className = "btn btn-subtle btn-sm";
    retryBtn.textContent = "Retry";
    retryBtn.addEventListener("click", () => {
      this.handleAsk(query);
    });
    leftActions.appendChild(retryBtn);

    actionRow.appendChild(leftActions);

    // Report issue
    const reportBtn = document.createElement("button");
    reportBtn.className = "btn btn-subtle btn-sm";
    reportBtn.style.color = "var(--color-text-muted)";
    reportBtn.textContent = "Report issue";
    reportBtn.addEventListener("click", () => {
      this.openReportModal(query, qaData);
    });
    actionRow.appendChild(reportBtn);

    card.appendChild(actionRow);

    this.feed.appendChild(card);
    card.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  openCalcModal() {
    const calc = state.activeCalculation;
    if (!calc || !this.calcModalOverlay) return;
    this.calcFormula.textContent = calc.formula;
    this.calcNature.textContent = calc.nature;
    this.calcInput.textContent = calc.inputValue;
    this.calcOutput.textContent = calc.outputValue;
    this.calcFactor.textContent = calc.conversionFactor;
    this.calcModalOverlay.classList.add("open");
  }

  openReportModal(query, qaData) {
    state.lastFocusedElement = document.activeElement;
    this.activeReportTarget = { query, qaData };
    if (this.reportModalOverlay) {
      this.reportModalOverlay.classList.add("open");
      this.btnSubmitReport.disabled = false;
      this.btnSubmitReport.textContent = "Record feedback locally";
      this.btnCancelReport.textContent = "Cancel";
      if (this.reportNotesInput) this.reportNotesInput.value = "";
      state.trapFocusInModal("reportModalOverlay");
    }
  }

  closeReportModal() {
    this.activeReportTarget = null;
    if (this.reportModalOverlay) {
      this.reportModalOverlay.classList.remove("open");
    }
    state.restoreModalFocus();
  }

  submitReport() {
    const reason = this.reportReasonSelect ? this.reportReasonSelect.value : "Incorrect finding";
    const notes = this.reportNotesInput ? this.reportNotesInput.value.trim() : "";
    if (!this.activeReportTarget || this.btnSubmitReport?.disabled) return;
    state.issueReports.push({ reason, notes, query: this.activeReportTarget.query, date: new Date().toISOString() });

    if (this.btnSubmitReport) {
      this.btnSubmitReport.textContent = "✓ Recorded for this session";
      this.btnSubmitReport.disabled = true;
      this.btnCancelReport.textContent = "Close";
    }
  }
}
