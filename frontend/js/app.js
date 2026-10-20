/* ==========================================================================
   EVID APPLICATION BOOTSTRAPPER
   Tab Routing, Shell Controller, Controller Orchestration, Accessibility
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
  // 1. Initialize Subsystem Controllers
  const viewerController = new EvidenceViewerController();
  const documentsController = new DocumentsController();
  const askController = new AskController();
  const extractController = new ExtractController();
  const compareController = new CompareController();
  const uploaderController = new UploaderController();
  const workflowsController = new WorkflowsController();

  // 2. Tab Navigation Elements
  const tabButtons = document.querySelectorAll(".nav-tab");
  const views = {
    documents: document.getElementById("viewDocuments"),
    ask: document.getElementById("viewAsk"),
    extract: document.getElementById("viewExtract"),
    compare: document.getElementById("viewCompare"),
  };

  const sidebar = document.getElementById("appSidebar");
  const btnToggleSidebar = document.getElementById("btnToggleSidebar");
  const mobileMenu = document.getElementById("btnMobileMenu");
  const backdrop = document.getElementById("sidebarBackdrop");
  const workspace = document.getElementById("workspaceContainer");
  const mobileLayout = window.matchMedia("(max-width: 768px)");
  const sidebarLinks = {
    documents: document.getElementById("sidebarNavDocs"),
    ask: document.getElementById("sidebarNavAsk"),
    extract: document.getElementById("sidebarNavExtract"),
    compare: document.getElementById("sidebarNavCompare"),
  };

  function setMobileNavigation(open, restoreFocus = false) {
    const isOpen = mobileLayout.matches && open;
    sidebar.classList.toggle("mobile-open", isOpen);
    sidebar.classList.toggle("collapsed", !mobileLayout.matches && state.sidebarCollapsed);
    sidebar.inert = mobileLayout.matches && !isOpen;
    backdrop.hidden = !isOpen;
    workspace.inert = isOpen;
    mobileMenu.setAttribute("aria-expanded", String(isOpen));
    mobileMenu.setAttribute("aria-label", isOpen ? "Close navigation" : "Open navigation");
    btnToggleSidebar.setAttribute("aria-expanded", String(mobileLayout.matches ? isOpen : !state.sidebarCollapsed));
    btnToggleSidebar.setAttribute("aria-label", mobileLayout.matches ? "Close navigation" : state.sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar");
    if (isOpen) sidebarLinks[state.activeTab]?.focus();
    else if (restoreFocus) mobileMenu.focus();
  }

  function syncNavigation() {
    document.getElementById("taskArea").scrollTop = 0;
    tabButtons.forEach((btn) => {
      const active = btn.dataset.tab === state.activeTab;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-selected", String(active));
      btn.tabIndex = active ? 0 : -1;
    });
    Object.entries(sidebarLinks).forEach(([key, btn]) => {
      const active = key === state.activeTab;
      btn.classList.toggle("active", active);
      if (active) btn.setAttribute("aria-current", "page");
      else btn.removeAttribute("aria-current");
    });
    Object.entries(views).forEach(([key, view]) => {
      view.style.display = key === state.activeTab ? "flex" : "none";
    });
  }

  function switchTab(targetTab) {
    if (!views[targetTab]) return;
    state.setActiveTab(targetTab);
    if (sidebar.classList.contains("mobile-open")) {
      setMobileNavigation(false);
      document.querySelector(`.nav-tab[data-tab="${targetTab}"]`)?.focus();
    }
  }

  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      switchTab(btn.dataset.tab);
    });
    btn.addEventListener("keydown", (event) => {
      const keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
      if (!keys.includes(event.key)) return;
      event.preventDefault();
      const tabs = [...tabButtons];
      const index = tabs.indexOf(btn);
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 :
        (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      switchTab(tabs[next].dataset.tab);
      tabs[next].focus();
    });
  });

  // Sidebar Toggle
  if (btnToggleSidebar) {
    btnToggleSidebar.addEventListener("click", () => {
      if (mobileLayout.matches) setMobileNavigation(false, true);
      else state.toggleSidebar();
    });
  }
  mobileMenu.addEventListener("click", () => setMobileNavigation(!sidebar.classList.contains("mobile-open")));
  backdrop.addEventListener("click", () => setMobileNavigation(false, true));
  mobileLayout.addEventListener("change", () => setMobileNavigation(false));
  setMobileNavigation(false);

  document.addEventListener("keydown", (event) => {
    if (!sidebar.classList.contains("mobile-open") || state.activeModal) return;
    if (event.key === "Escape") {
      event.preventDefault();
      setMobileNavigation(false, true);
    } else if (event.key === "Tab") {
      const focusable = [mobileMenu, ...sidebar.querySelectorAll("button:not(:disabled)")];
      const index = focusable.indexOf(document.activeElement);
      const next = event.shiftKey ? index - 1 : index + 1;
      event.preventDefault();
      focusable[(next + focusable.length) % focusable.length].focus();
    }
  });

  // Sidebar Navigation Links
  const sidebarDocsBtn = document.getElementById("sidebarNavDocs");
  if (sidebarDocsBtn) {
    sidebarDocsBtn.addEventListener("click", () => switchTab("documents"));
  }
  const sidebarAskBtn = document.getElementById("sidebarNavAsk");
  if (sidebarAskBtn) {
    sidebarAskBtn.addEventListener("click", () => switchTab("ask"));
  }
  const sidebarExtractBtn = document.getElementById("sidebarNavExtract");
  if (sidebarExtractBtn) {
    sidebarExtractBtn.addEventListener("click", () => switchTab("extract"));
  }
  const sidebarCompareBtn = document.getElementById("sidebarNavCompare");
  if (sidebarCompareBtn) {
    sidebarCompareBtn.addEventListener("click", () => switchTab("compare"));
  }

  // Sidebar Footer: Settings and Help
  const btnSettings = document.getElementById("btnSidebarSettings");
  if (btnSettings) {
    btnSettings.addEventListener("click", () => {
      setMobileNavigation(false);
      if (mobileLayout.matches) mobileMenu.focus();
      state.openSettings();
    });
  }
  const btnCloseSettings = document.getElementById("btnCloseSettingsModal");
  if (btnCloseSettings) {
    btnCloseSettings.addEventListener("click", () => state.closeSettings());
  }
  const btnClearWorkspace = document.getElementById("btnClearWorkspace");
  if (btnClearWorkspace) {
    btnClearWorkspace.addEventListener("click", async () => {
      if (!window.confirm("Clear every PDF and result in this browser workspace? This cannot be undone.")) return;
      btnClearWorkspace.disabled = true;
      try {
        await state.clearWorkspace();
        state.closeSettings();
      } catch (error) {
        window.alert(error.message || "This workspace could not be cleared.");
      } finally {
        btnClearWorkspace.disabled = false;
      }
    });
  }

  const btnHelp = document.getElementById("btnSidebarHelp");
  if (btnHelp) {
    btnHelp.addEventListener("click", () => {
      setMobileNavigation(false);
      if (mobileLayout.matches) mobileMenu.focus();
      state.openHelp();
    });
  }
  const btnCloseHelp = document.getElementById("btnCloseHelpModal");
  if (btnCloseHelp) {
    btnCloseHelp.addEventListener("click", () => state.closeHelp());
  }

  state.subscribe((event) => {
    if (event === "sidebar_toggle") {
      setMobileNavigation(false);
    } else if (event === "tab_change") {
      syncNavigation();
    }
  });

  // Global Keyboard Shortcuts
  document.addEventListener("keydown", (e) => {
    if (e.altKey) {
      if (e.key === "1") switchTab("documents");
      if (e.key === "2") switchTab("ask");
      if (e.key === "3") switchTab("extract");
      if (e.key === "4") switchTab("compare");
    }
  });

  // Initial tab setup
  switchTab("documents");
  state.loadUploadedDocuments();

  console.log("Evid Document Intelligence UI successfully initialized.");
});
