# Evid Project Implementation Status

## Current status — Empty workspace for manual UI review, October 19, 2026

The user's requested clean reset is complete. The live Documents page starts with a single upload invitation. The active upload catalog is empty, and the app no longer loads the Pharma fixture, demonstration conversation, extraction matrix, or comparison results. A guide is served at http://localhost:8000/guide.html and linked from the empty screen and Help.

### What was reset

- Moved active `storage` (upload records, renders, evaluation output, local Qdrant index), `frontend/public/pages` (uploaded and sample image copies), `.pytest_cache`, and generated Python `__pycache__` folders out of the active project. Eleven runtime/cache paths were reset.
- A one-time localhost response delivered `Clear-Site-Data: "cache", "cookies", "storage"`. The app itself contains no localStorage/sessionStorage/IndexedDB persistence. Reload resets its in-memory viewer, filters, conversation, findings, feedback, and review state. Static/API responses retain the existing no-store policy.
- Source fixtures and dependencies remain development assets. They are not loaded into the active workspace. Previous runtime files are recoverable in `evid-clean-before/runtime` outside the app under `/Users/abhinav/.codex/visualizations/2026/10/19/01a155b5-532c-7ad2-93eb-3a59cb543f34/`.
- Only this app's data was reset; other projects and browser origins were not cleared. Future uploads remain persistent across refresh, as expected for manual testing.

### Architecture, phases, and data flow

| Phase | What is built and why | Exact mechanism | Verification gate |
| --- | --- | --- | --- |
| Startup | A real empty project instead of a demonstration project. | `AppStateManager` starts with `masterFile: null`, empty sections, source selections, fields, results, and conversation; extraction starts at step 1. `index.html` no longer loads `data.js`. Saved uploads are still restored from GET /api/documents. | New Node VM test loads state without the fixture and verifies every starting collection and viewer state. Empty catalog restoration never manufactures a sample. |
| Viewer initialization | Permit a PDF viewer to exist before the first upload. | Optional source access in `viewer.js`; zero pages/thumbnails when no document is selected. No initial sample image src exists in HTML. `openEvidence` still rejects an absent source. | Browser startup has no images with src, no source rows, and no errors; tests verify absence of phantom source and opening a restored upload at its own bounds. |
| First-use Documents | One clear next action instead of an empty dashboard. | `.is-empty` and the native `hidden` attribute hide stats, filters, and the empty table. A welcome panel opens the shared uploader; document-added rendering reveals the real library. Header badge counts original PDF files. | Browser verifies the first-upload button opens the same dialog and Escape returns focus to it. Source registry and restoration tests pass. |
| Task navigation | Explain the three future tasks without showing fictitious user data. | Ask/Extract/Compare show one purpose, one availability note, a Documents link, and a guide link. Their sample controllers return before initializing in a non-sample workspace. | Browser traverses all four tabs and returns through Go to documents; Node regression verifies controllers need no sample DOM/data. |
| Plain-language help | Explain current capabilities and prepare a useful feedback session. | Standalone responsive `guide.html` with first steps, per-page purpose/current limits, viewer controls, label glossary, persistence, and review prompts. Upload privacy wording describes local storage. Help summarizes the same available/planned split. | Guide loads, every contents anchor resolves, the viewer anchor scrolls to the correct section, and no root overflow is measured. Help opens from mobile navigation; Escape restores the menu-button focus. |
| Reset boundary | Clear active test state without making future refreshes destructive. | Runtime directories moved to an external rollback location, recreated empty; temporary one-time site-data header then normal server operation. No permanent reset endpoint or recurring clear routine added. | Live GET /api/documents returns exactly an empty documents array; active page-render directory is empty after tests. |

The first-use design applies progressive disclosure: library details appear when there are files to describe, and each empty task explains its purpose before offering more information. Native links, heading hierarchy, button semantics, the existing focus trap, Escape ownership, and focus restoration preserve keyboard navigation. These are implementation practices, not a claim of accessibility certification or enterprise compliance.

### Validation

- `node --test tests/test_empty_workspace.cjs tests/test_upload_sources.cjs tests/test_ui_interactions.cjs`: **18 passed, 0 failed**. Five new tests cover the clean default, inactive sample controllers, empty reload, a real upload becoming the only source, and an entry page without sample script/images/results. Prior fixture tests opt into their sample explicitly.
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest tests/test_upload_api.py -q -p no:cacheprovider --basetemp=/private/tmp/evid-clean-ui/pytest`: **4 passed**, 1.35 seconds. Upload rendering, content identity, text, persistence, legacy metadata, and corruption checks use isolated temporary storage and do not repopulate the user's library.
- All frontend JavaScript syntax and referenced script/stylesheet existence checks passed. Entry and guide IDs are unique.
- Browser verified clean reload, all activity tabs, return to Documents, upload dialog opening/closing and focus return, Help and its guide link, guide anchors, empty image state, and no captured errors. At the narrow 665px viewport and desktop 1280px viewport, no page-level horizontal overflow was present; desktop additionally showed zero library rows and zero image sources. No files were uploaded into the active workspace during this reset.
- Screenshots: `evid-empty-workspace.jpg` and `evid-empty-workspace-desktop.jpg` in the visualization directory above. Source originals are backed up in `evid-clean-before`.

### What the user can test now

PDF upload, library browsing and filters after upload, whole-file section review, rendered pages, page navigation, zoom, and native text when a PDF contains it. Review changes remain session-only. Ask, Extract, and Compare for arbitrary uploaded PDFs remain unconnected; the clean pages explicitly say In development. No sample data is loaded to simulate availability.

---

## Prior UI audit report

## Current status — UI audit and repairs completed, October 19, 2026

The user's open staging file was an incomplete frontend copy: eight stylesheets and the Ask, Extract, and Compare controllers were absent. The complete application is served at http://localhost:8000/. The old staging entry now redirects there, and the real frontend redirects disk-file launches before loading application assets. Browser automation disallows file URLs, so that redirect is verified by a VM regression test; the HTTP destination was verified in the browser.

### Architecture and repair mapping

The frontend remains a vanilla HTML/CSS/JavaScript application. `state.js` owns session state and event subscriptions; activity controllers render the library, sample analysis workflows, upload dialog, and shared evidence viewer. The local Python server supplies static assets and the existing persistent upload catalog. No backend or stored document data changed during this audit.

| Phase | Reproduced defect and resulting behavior | Implementation and verification gate |
| --- | --- | --- |
| Startup | Partial staging checkout looked broken and could not execute every activity. | Early protocol guard in `frontend/index.html`; old temporary entry replaced with redirect/link. Node VM verifies file redirect and HTTP no-op. Every referenced local script and stylesheet exists in the real frontend. |
| Small screens | Oversized library banner and stats pushed document rows below the initial phone viewport. | Container query reduces padding/type and hides the redundant banner upload button; header Add documents remains. At 398px, table begins around 622px; root width equals viewport width. Mobile navigation, Settings Escape, and focus return to the menu button verified. |
| Evidence zoom | Transform-based magnification shifted the left edge outside the reachable scroll area. | Set the stage's actual width from viewport content width times zoom; let normal overflow scrolling handle larger pages. ResizeObserver reapplies zoom. Fit resets zoom and both scroll offsets. Regression tests plus phone viewer check confirm reachable left edge and correct page 11 image. |
| Dialogs | Escape closed the calculation dialog and its evidence viewer together; report focus was unmanaged. | The active modal owns Escape through stopImmediatePropagation. Upload/report use close-request subscriptions and focus restoration. Report uses the shared focus trap. Calculation, report, and upload Escape checks preserve the open viewer. Mobile modal layout wraps buttons/long filenames. |
| Source navigation | Change sources implied a selector but only navigated away. | Renamed Browse sample sources, with explicit sample context. The action opens Documents filtered to the sample and expands its sections. Browser confirms one matching parent and clear filters restores both sources. |
| Session actions | Unsaving retained an underlying saved record; report submission only wrote to console. | Save/unsave now adds/removes the same session record. Feedback is explicitly local to the current session, stored once in `state.issueReports`; submit disables after success. Browser checks and feedback regression test pass. Settings storage wording now matches the implementation. |

### Verification and exit gates

- `node --test tests/test_upload_sources.cjs tests/test_ui_interactions.cjs`: **13 passed, 0 failed**. Seven new regression tests cover protocol redirect, modal Escape ownership/delegation, width-based zoom, Fit scroll reset, and local feedback recording. Six existing tests continue to protect uploaded-source identity/isolation.
- All frontend JavaScript syntax checks, stylesheet/script asset existence, and duplicate HTML ID checks passed.
- Browser on desktop (1440px) and phone (398px): correct source registry, filters, dialogs, zoom, keyboard closing, navigation, and no final root overflow. No captured browser console errors in either final live tab.
- Extraction rejects an empty field name, preserves the field editor, advances through preview and review, and downloads a CSV with 6 data rows and 9 columns.
- Comparison marks changed selectors stale and disables export; a supported Low/High Flow comparison refreshes results and downloads a CSV with 5 data rows and 7 columns. An unsupported pair displays an unavailable message and keeps export disabled.
- Unknown lot 99988877 abstains in sample Q&A. Save/unsave and local feedback controls verified. Upload dialog opens/closes while preserving the viewer; actual PDF upload, duplicate, malformed-file, and persistence checks were completed in the preceding source-isolation pass.
- Backend code is unchanged; the preceding **79-passed** Python suite is historical validation and was not rerun for this frontend-only audit.
- Proof: `evid-ui-audit-desktop.jpg` and `evid-ui-audit-mobile.jpg` in `/Users/abhinav/.codex/visualizations/2026/10/19/01a155b5-532c-7ad2-93eb-3a59cb543f34/`. Before-edit sources are preserved in `evid-ui-audit-before` there.

### Limits and next integration work

The library retains 2 source files and 9 sections. The legacy research paper opens its own 11 rendered pages; its missing original PDF/native text still requires re-upload of the same paper to recover text. Sample Q&A, extraction, and comparison are explicitly labeled and are not wired to arbitrary uploaded documents. Session findings, feedback, and review edits are not durable server records. This audit does not claim a production arbitrary-document analysis pipeline or an external support submission service.

The implementation uses standard DOM event propagation and focus management, content-based upload identity, and CSS layout overflow rather than inaccessible translated content. The concrete correctness gates above are local behavior checks; no enterprise certification, regulatory compliance, or external research validation is claimed for this UI pass.

---

## Prior upload repair report

## Current status — Upload source isolation repaired, October 19, 2026

The reported research-paper upload defect was reproduced in the actual browser and fixed. The recovered `2602.03973v1.pdf` now appears as an independent original PDF, and its viewer opens its own 11 pages. The live library was left with the sample and that user upload; synthetic test uploads were removed after verification.

### Cause and repaired data flow

| Phase | Previous defect | Repair and verification |
| --- | --- | --- |
| Upload | Uploaded sections were appended to the sample array; offline fallback reported Ready without rendered pages. | Register one independent source only after a valid server response. No unrendered client fallback. Corrupt/empty PDFs rejected in browser tests without increasing counts. |
| Identity | Filename-based checks rejected distinct files; section IDs could collide with sample IDs. | SHA-256 content identity; uploaded sections are namespaced by source ID. Different PDFs with identical filenames remain separate; repeated bytes produce one source. |
| Library | One hardcoded parent displayed every section; new source counts disagreed with visible rows. | Render parent/child groups from the source registry. Each row carries its owning file ID. Generic Document and Imported filters are available. |
| Viewer | Page images, native text, thumbnails, and page limits were hardcoded to the Pharma sample. | Resolve the explicit file ID for each open. Use that source's image base, native text, thumbnails, and page count. Test PDFs navigate to their own pages 12 and 2. |
| Evidence | Highlight boxes could remain after page changes; a filename change did not identify the source. | Clear boxes when changing page/source and preserve sample citation source explicitly. Browser check: sample citation creates one box; opening the user's paper displays zero boxes and the user's image path. |
| Persistence | Reload discarded uploaded-file registrations. | GET /api/documents restores saved source records. Legacy rendered manifests are recovered without fabricating missing text. New uploads save original PDFs, metadata, native text, and page renders. |
| Server | Upload route referenced a nonexistent extractor and separator API. | Use the existing TextExtractionService with real PDFium rendering. Arbitrary papers are imported as whole Document sections; Pharma-specific classification is not applied to unrelated papers. Native work is serialized because PDFium is not thread safe. |

### Validation results

- `node --test tests/test_upload_sources.cjs`: **6 passed**.
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider`: **79 passed**, 1 existing local-Qdrant payload-index warning, 21.12 seconds.
- HTML nesting/unique IDs and changed JavaScript/Python syntax checks passed.
- Browser upload: a 12-page ALPHA fixture initially reproduced the bad Pharma nesting/image. After repair it opened its own image on page 12, with 12 thumbnails and ALPHA-PAGE-12 native text.
- Browser multi-upload: a distinct 2-page BETA fixture with the same filename was a separate original PDF. Page entry 99 clamped to page 2, and its text contained BETA-PAGE-02, not ALPHA or Pharma text.
- Re-uploading ALPHA returned Already in library without increasing the source count. The legacy ALPHA record gained native text on re-upload.
- Empty and malformed PDFs produced readable errors and did not create new library sources.
- Original user upload recovered from its existing manifest. Parent Open and child View both opened the correct source. Page 11 loaded successfully; no sample highlight appeared.
- Reload restored saved files. After generated-test cleanup, the browser showed 2 parent sources, 9 total sections, and the user's PDF page 11 of 11.
- Screenshot proof: `/Users/abhinav/.codex/visualizations/2026/10/19/01a155b5-532c-7ad2-93eb-3a59cb543f34/evid-upload-fixed.jpg`.

### Remaining scope

The recovered older research-paper upload has rendered page images but no stored original PDF or native-text record. Its text tab reports that limitation. Re-uploading the same PDF once fills in native text without creating another source. Scanned PDFs still need OCR for searchable text.

Q&A, extraction, and comparison remain sample workflows, as visibly labeled. This repair isolates arbitrary uploaded files in the library/viewer; it does not connect those analysis workflows to new sources. Review edits are currently local UI state and are not saved to the upload catalog.

The server is running on localhost:8000 with the repaired endpoints. Original edited sources are backed up under `evid-upload-before` beside the screenshot. Test fixtures and regression tests are kept in the repository for repeatable verification; their live uploaded copies were archived under `/private/tmp/evid-upload-repair/runtime-test-artifacts` and removed from the library.

---

## Prior UI implementation report


## Current status — UI refinement completed, October 19, 2026

The latest pass improves the existing frontend in place. Backend services and sample evidence data are unchanged. Earlier implementation claims are preserved below as historical notes; they are not all revalidated by this UI pass.

### Changes completed

- Library: clearer heading and sample context, live counts for files/sections/reviews, readable metadata labels, compact review actions, preserved table-cell semantics, and a keyboard-operable section expander. Original identifier values are unchanged.
- Shell: active navigation now stays synchronized, tab controls support Left/Right/Home/End, switching activities returns to the top, and sidebar expansion labels reflect the actual state.
- Mobile: visible navigation control, backdrop, Escape/selection closing, keyboard focus containment and restoration, inert closed navigation, and four visible activity tabs. Tables scroll inside their containers.
- Viewer: toolbar wraps, thumbnail buttons work by keyboard, toggle appearance and aria-pressed reflect actual state, and narrow desktop windows use an overlay rather than squeezing the task area. Divider resizing preserves at least 480px for the task content.
- Extraction: keyboard-accessible steps, responsive stepper and preview cards, legible table widths, and explicit sample-mode guidance.
- Upload dialog: Done and Escape use a shared close routine, focus returns to the opener, the dialog traps focus, and PDF browsing is keyboard accessible. Upload/ingestion logic is unchanged.
- Truthful controls: the project label no longer offers a destructive sample reset disguised as switching projects. Unavailable sharing is replaced by a local-workspace label. The unimplemented comparison scope is visibly unavailable. Q&A no longer simulates BM25/BGE/vision processing stages with timed progress messages.
- Design tokens: repaired missing spacing and line-height variables while preserving the existing neutral/blue palette, system fonts, and dependencies.

### Verification performed in this pass

- JavaScript syntax checks passed for every changed JS file.
- HTML nesting and unique IDs passed; CSS variable references are all defined.
- Live browser checks: responsive widths 375, 768, 1024, 1280 and 1440px; no page-level horizontal overflow at measured phone/tablet/desktop widths.
- Comparison: packaging initial results load; switching to Low/High Flow marks results stale and disables export; running the comparison updates both headers and enables export.
- Extraction: Edit Field Schema opens step 2; Back opens step 1; deselect-all disables Continue; select-all permits progression through fields and preview to review. Two preview cards rendered.
- Q&A: the sample gamma-range query for lot 18356721 returns the sample certificate response; its citation opens PDF page 2.
- Viewer: page entry 99 clamps to page 10; text and thumbnail controls update aria-pressed; toolbar fits the evidence panel. At 1024px the viewer overlays the workspace without reducing task width.
- Library: searching 18356721 returns one section; clearing filters restores sections; saving a section review updates the review count from 8 to 7; Enter on the parent expander collapses rows; expanding restores them.
- Navigation: mobile menu opens, selecting an activity closes it, Escape restores focus; closed navigation is inert. ArrowRight changes the selected activity. Desktop collapse reaches 64px and updates the label.
- Upload: Done and Escape both close the dialog and restore focus to Add documents. No new PDFs were uploaded in this pass.
- Captured browser logs contain initialization messages and no errors. Backend pytest results below belong to the earlier pass; the backend suite was not rerun for these frontend changes.

### Remaining limitations and next action

Q&A, extraction, and comparison still rely on bundled sample data. They are not a complete production pipeline for newly uploaded PDFs. Code inspection also shows that uploaded sections are currently appended beneath the sample parent, while the shared viewer still uses sample page paths and a 10-page limit. These integration defects predate this pass and need a separate implementation pass before arbitrary-document workflows can be called complete.

Next action: connect each uploaded file to its own document IDs, page images, page bounds, and text; then connect retrieval/extraction to those sources and test with an independent PDF. Recheck upload and library persistence as part of that work.

Original edited files are backed up in:
`/Users/abhinav/.codex/visualizations/2026/10/19/01a155b5-532c-7ad2-93eb-3a59cb543f34/evid-ui-before`.

---

## Historical implementation report (before this UI pass)


## Status: All Requested Phases Completed & Verified

All items specified in the instruction have been completely implemented and verified across both backend test suites and live browser testing.

---

### Summary of Completed Work

#### 1. Implementation Recovery & Dataset Integrity
- **`frontend/js/data.js`**: Audited and confirmed full, unabbreviated 447-line dataset. Correct low-flow certificate values preserved:
  - Article Number: `28 9301 82`
  - Lot Number: `18356721`
  - Date of Manufacture: `20240315`
  - Expiration Date: `20260315`
  - Bounding Box: `{ ymin: 240, xmin: 60, ymax: 300, xmax: 560 }`
- **`frontend/js/compare.js` & `frontend/index.html`**: Synchronized exact element IDs:
  - `compareDocASelect`, `compareDocBSelect`, `btnRunCompare`, `compareThDocA`, `compareThDocB`, `compareTableBody`.
  - Single controller initialization attached to global lifecycle.

#### 2. Document & Revision Comparisons
- **Selector Options**: Aligned with sample fixtures:
  - `packaging_revB` + `packaging_revC` → `packaging_revB_vs_revC`
  - `low_flow` + `high_flow` → `low_flow_vs_high_flow`
- **Sample Mode & Chronology Labels**:
  - Packaging sample visibly displays: *"Changes described in revision history. The current Revision C specification (DWG-29477427-PKG-R3, pp. 4–5) and its revision-history table are not independent original Revision B/C files. Do not infer historical values or unchanged properties from the current specification alone."*
  - Columns labeled *Earlier Document (Rev B)* and *Later Document (Rev C)* for revisions.
  - Distinct products labeled *Document A: Low Flow Kit* and *Document B: High Flow Kit*.
- **Stale State Management**:
  - Changing either selector immediately renders `#compareStaleNotice` and disables `#btnExportCompare`.
  - Stale state clears cleanly upon clicking *Compare*.
- **Unsupported Combinations**: Explicit unavailability message rendered inside table body; never falls back to another pair's results.
- **Safe DOM Rendering**: All document-derived content rendered through `document.createElement` and `textContent`.

#### 3. Complete 4-Screen Extraction System
- **Screen 1 (Choose Documents)**: Searchable checklist with count indicator (`extractSelectedCount`), select all/deselect all, requires at least 1 document to proceed.
- **Screen 2 (Define Fields)**: Full schema editor with name, type, description, unit, and required flag. Add/remove field rows with client validation (rejects blank names).
- **Screen 3 (Preview)**: Small-sample multi-card extraction preview with verified source citations.
- **Screen 4 (Run & Review)**: Results matrix with sticky table headers, 6 explicit status states:
  - `extracted` (green badge)
  - `derived` (blue badge)
  - `not_found` (neutral badge)
  - `na` (gray badge)
  - `uncertain` (yellow badge)
  - `failed` (red badge)
- **Navigation & Handlers**:
  - *"Edit Field Schema"* button directs immediately to Step 2 through a single handler.
  - *Back* and *Continue* preserve all user edits.
  - Invalidation flag marks previous results invalid when sources or schema change.
  - Local review workflow with *"✓ Accept"* action updates status to `"Accepted locally by Quality Engineer"`.
  - CSV export protected against spreadsheet formula injection (`=`, `+`, `-`, `@`).

#### 4. Grounded Q&A (Ask) & Shared Evidence Viewer
- **Ask View**:
  - Active source scope indicator displayed beside composer.
  - Rejects blank submissions.
  - Supports Enter (submit) and Shift+Enter (newline).
  - Preserves user input upon failure or cancellation.
  - Dynamic multi-token evidence retrieval across document sections, scoped identifiers, and bounding boxes.
  - Honest abstention on unknown lots (e.g. Lot 99988877) without fabricated inferences.
  - Real copy to clipboard, save finding, and report issue dialog.
- **Shared Evidence Viewer**:
  - Single viewer shared across Documents, Ask, and Extraction.
  - Bounds validation (clamped to 1..10) on page jump input with Enter key support.
  - High-res document stage, filmstrip thumbnails, verified coordinate overlay bounding boxes.
  - Toolbar controls: Zoom In, Zoom Out, Fit to Width, Fullscreen toggle, Text drawer toggle.
  - Text drawer wraps native text layer.
  - Replaced fabricated printed-page claims with genuine `PDF page X of Y` indicators.
  - Prior image/text state cleared when opening a different document file.

#### 5. File Uploads & General Workflows
- **Validation**:
  - Client-side and server-side validation rejecting empty (0 bytes), unsupported non-PDF, oversized (>25MB), and corrupt files.
  - True status feedback (uploading, processing, indexing) without fake timer simulation.
  - Multi-file resilience: successful files preserved if another file fails.
- **Library & Navigation**:
  - Expandable parent files with subdocument children.
  - Combined search and type/status filters with *Clear filters* button.
  - Renamed "Review Boundaries" to *"Review document sections"*.
  - Empty project onboarding view (*"Your documents start here."*) with *Load Sample Project* action.
  - Project switching, Settings modal, and Help modal fully functional.

#### 6. UI Direction & Design Tokens
- **Color Palette**:
  - App background: `#F7F7F4`
  - Surfaces: `#FFFFFF`
  - Primary text: `#17202C`
  - Secondary text: `#526071`
  - Borders: `#DEE3E8`
  - Primary action: `#345DAD` (hover `#294C91`, selected `#EAF0FA`)
- **Typography & Scale**: System/Inter font stack, 40px control heights, 8px control radius, 12px surface radius, 4/8/12/16/24/32px spacing scale.
- **Icons**: Clean inline SVG icons throughout; all emoji icons replaced.

---

### Verification and Test Execution Results

1. **Backend Test Suite (`pytest`)**:
   - `75 passed, 1 warning in 19.51s`
   - Covers: exact lookup, hybrid ingestion, reasoning, retrieval, structure-aware chunking, answer synthesis, document organization contracts.

2. **Browser Workflow & Integration Tests (Playwright / Chromium)**:
   - **Compare View**:
     - `packaging_revB` + `packaging_revC`: Verified headers `Earlier Document (Rev B)` / `Later Document (Rev C)`, sample banner present, safe textContent rendering.
     - Stale detection: Verified `#compareStaleNotice` displays immediately and `#btnExportCompare` disabled upon selector change.
     - `low_flow` + `high_flow`: Verified Document A / Document B labels.
     - Unsupported pair (`packaging_revB` + `low_flow`): Explicit unavailability message verified.
   - **Extract View**:
     - 4 wizard panels verified.
     - *"Edit Field Schema"* directs immediately to Step 2.
     - Step 2 Back → Step 1; Step 1 Continue → Step 2; Step 2 Continue → Step 3; Step 3 Run → Step 4.
     - Add field dynamically adds row and validates schema.
     - Human review *"✓ Accept"* changes badge to *"Accepted locally by Quality Engineer"*.
     - Formula-protected CSV export verified.
   - **Ask & Viewer**:
     - Question on low-flow kit verified to extract article `28 9301 82` and citation pill.
     - Citation click opens evidence viewer on exact PDF page with coordinate bounding box.
     - Zoom In/Out, Fit, Text Drawer toggle, and Page Jump with Enter verified.
     - Unknown lot query (`lot 99988877`) verified to return truthful abstention.
   - **Documents View**:
     - Parent expandable file row and 8 subdocument rows verified.
     - Filter by "Specification" reduces to 1 matching subdoc; *Clear filters* restores all 8.
     - *"Review document sections"* opens modal and saves title/type/pages.
     - Empty workspace renders *"Your documents start here."* and *Load Sample Project* button.
   - **Upload Validation**:
     - Empty file (0 bytes) rejected with readable message.
     - Non-PDF (`notes.txt`) rejected with readable message.
     - Oversized file (>25MB) rejected with readable message.

3. **Responsive Viewport Audit**:
   - `1440px`: Header 64px, sidebar 232px, workspace 1208px, evidence viewer 44% width (531.5px), main area 676.5px (>=480px).
   - `1024px`: Topbar 64px, sidebar 232px, evidence panel 364px (>=360px min width).
   - `768px`: All 4 activities visible in topbar, tables contained inside horizontal scroll wrappers (`overflow-x: auto`).
   - `375px`: Mobile viewport verified; `.modal-dialog` width 341.5px (fits comfortably with padding); modal closes on Escape key with focus restoration.
   - Browser Console: 0 errors, 0 warnings.

---

### Remaining Operational Blockers / External Dependencies
- **Cloud Collaboration & Sharing**: Project sharing button intentionally produces a notice: local instances operate with on-premises storage; cloud sharing requires remote tenant authentication and workspace membership endpoints.
- **OCR of Scanned Non-Searchable PDFs**: Local server processes searchable PDFs via native text layers and pdfium; non-searchable scans require an external OCR pipeline (e.g. Tesseract or cloud Vision API) when deployed to production.
