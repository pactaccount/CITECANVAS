# CiteCanvas: An Anonymous, Evidence-Linked PDF Analysis Workspace

**Technical Implementation and Evaluation Report**
**Project:** CiteCanvas
**Release:** 1.0

## Abstract

CiteCanvas is a web application for asking evidence-linked questions about PDF
documents, constructing review tables, and comparing files without requiring a
user account. The implementation combines a browser-scoped anonymous workspace,
durable object and metadata storage, hybrid retrieval, vision-language analysis,
and traceable deployment controls. The central design objective is to preserve a
simple demonstration workflow while preventing one visitor's workspace from
appearing in another visitor's browser. This report describes the requirements,
architecture, implementation decisions, validation carried out before release,
observed limitations, and future evaluation work.

**Index Terms—** document intelligence, retrieval-augmented generation (RAG),
PDF analysis, evidence grounding, anonymous workspace, Cloudflare R2,
PostgreSQL, Qdrant, OpenTelemetry.

## I. Introduction

Many document-analysis tools require accounts, configuration, and technical
knowledge before a user can inspect a report. CiteCanvas focuses on the smaller
interaction: upload a PDF, view its pages, ask a question, build a table, or
compare it with another document. Results must identify the supporting source
page so that a reader can inspect the evidence rather than accept an unsupported
model response.

The product is designed for demonstrations and short-lived collaborative review.
It intentionally has no login system. A browser session becomes the workspace
boundary, while persistent services retain the workspace only for the configured
inactive lifetime.

## II. Requirements and Use Cases

The implementation was guided by five requirements:

1. A first-time visitor must be able to use the product without registration.
2. Tabs opened in the same browser profile must share the same workspace.
3. A different browser profile must begin with an empty workspace and must not
   receive another visitor's files.
4. Uploaded PDFs, rendered pages, metadata, and retrieval data must survive a
   service restart during the workspace lifetime.
5. Answers, extracted tables, and comparisons must remain tied to inspectable
   document pages.

Representative use cases include technical-report review, due-diligence
comparison, research-paper interrogation, and checking high-cost modifications
in an automotive build sheet. These tasks require readers to move quickly from a
claim to its PDF evidence.

## III. Architecture and Design

### A. Workspace Boundary

On the first request, the server issues an opaque `HttpOnly` browser cookie. The
cookie selects an anonymous workspace; it is not a user identity and is never
exposed to page JavaScript. Browser tabs in the same profile send the same
cookie, whereas an incognito window or another profile starts a different
workspace. The server enforces the workspace identifier on document, retrieval,
and storage operations. In production, a 24-hour inactive-workspace expiry is
configured by `EVID_WORKSPACE_TTL_HOURS`.

This design improves isolation for the no-login use case, while acknowledging a
fundamental browser constraint: closing a browser cannot reliably notify a web
server. The session cookie ends browser access and the expiry task removes remote
objects and metadata after inactivity.

### B. Durable Storage

Cloudflare R2 stores original PDFs and rendered page images. The service uses
its S3-compatible API [1], which permits the same application code to use an
object-storage client in the hosted release. Neon PostgreSQL stores workspace,
document, object-key, content-hash, and expiry metadata. The content hash and
database uniqueness rule make a repeated upload idempotent instead of creating
multiple copies.

On restart, the server retrieves workspace metadata from PostgreSQL and restores
the short-lived local cache from R2. This separates durable user data from a
Render container's ephemeral filesystem.

### C. Retrieval and Grounding

Native PDF text is extracted where available and page images are rendered for
visual questions. BM25 provides a local lexical retrieval path. Qdrant stores
semantic vectors with workspace and document payload fields. Payload indexes are
used for filtered retrieval, consistent with Qdrant's guidance for frequently
filtered fields [2]. NVIDIA embedding and vision-language endpoints provide
semantic retrieval and visual interpretation; the selected embedding model
supports distinct query and passage inputs [3].

The answer workflow passes selected source material to the model and returns
page-linked evidence. If usable evidence is unavailable, the application
abstains instead of substituting a sample answer.

### D. Reproducible and Observable Release

The Dockerfile installs pinned Python dependencies, runs database migrations,
and starts a non-root application process. `render.yaml` defines the hosted
service, health check, and expected secret names. Render Blueprints provide a
repository-defined deployment configuration [4]. Migrations are idempotent so a
restart or redeploy can repeat them safely.

OpenTelemetry is optional and disabled until an OTLP endpoint is configured. The
application sends operation timing, status, and safe counts only; PDF text,
questions, answers, filenames, workspace tokens, and secrets are excluded. The
standard Python exporter supports OTLP HTTP/protobuf configuration [5], allowing
the deployment to use a self-hosted or managed collector without changing the
application.

### E. Performance-Preserving Ingestion and Retrieval

The release separates readiness from evidence fidelity. The immutable original
PDF remains in R2. During upload, CiteCanvas creates a fast, lossless 180-DPI
page preview and transfers page objects with a bounded four-request R2 pool.
When the source viewer, citation crop, or visual model needs a page, the server
creates and caches a lossless 300-DPI evidence render from the original PDF.
Thus, upload latency is reduced without replacing the underlying source or
reducing visual-verification resolution.

Answering uses a cascade. Specific factual questions use native text and BM25
to select one economical first candidate, which is still checked by the vision
model against a 300-DPI evidence page. Broad research questions, including
evaluation and comparison requests, expand related result vocabulary (for
example, *metrics* to *success rate* and *inference time*), inspect a bounded
set of relevant pages, and return individually source-linked findings. This
prevents an experimental setting or a baseline from being presented as an
evaluation metric. If verification is inconclusive, CiteCanvas falls through to
the existing visual semantic retrieval and evaluates the remaining candidates. Qdrant is
queried before a document's page vectors are regenerated or uploaded, preventing
the former repeated upsert on later questions. This preserves visual retrieval
for scans, tables, charts, and diagrams while avoiding it when a direct
text-backed answer is already available. The design follows the retrieval-stage
separation used in visual document research [6], [7].

## IV. Implementation

The frontend is a lightweight browser application with guided actions for
uploading, asking, table building, comparison, source viewing, and help
documentation. The backend is a Python HTTP service whose API is scoped by the
anonymous workspace cookie. The storage adapter has two modes: local filesystem
mode for development and R2/Neon mode for production. Qdrant and NVIDIA clients
remain configurable by environment variables so credentials are not placed in
source control.

The final repository removes an earlier unused EvidenceOps scaffold, obsolete
fixture sets, duplicate sandbox files, disconnected evaluators, and their tests.
The retained source tree contains only the runtime server, PDF ingestion,
grounding, retrieval, persistent-storage, observability, migrations, focused
fixtures, and focused regression tests needed by CiteCanvas.

## V. Release Evaluation

Table I records release validation. These checks prioritize concrete production
risks over repeated model calls. The RAG content test used one controlled BMW
build-sheet question: “Which modification costs the most?” It identified forged
wheels and linked the relevant first source page. This verifies one end-to-end
grounded answer, not a general accuracy claim.

**TABLE I. RELEASE VALIDATION**

| Check | Method | Result |
| --- | --- | --- |
| Focused regression suite | Upload API and runtime tests | 10 tests passed |
| R2/Neon recovery | Store a synthetic PDF, remove local cache, hydrate, read page, clean up | Passed |
| Idempotent migration | Apply the production migration twice | Passed |
| Docker release check | Build sanitized image; verify no `.env`; run migrations and focused tests | Passed |
| Controlled grounded question | One BMW query through the configured model service | Passed; forged wheels identified with page evidence |
| Browser isolation check | Same-profile tab versus private-profile session | Expected shared versus empty workspace behavior observed |
| Preview-render benchmark | 12-page fixture, local CPU only | 300-DPI optimized PNG: 0.874 s; 180-DPI fast PNG: 0.073 s |

The present evaluation does not establish retrieval recall, answer accuracy, or
latency percentiles across a representative corpus. A follow-on study should use
a versioned, rights-cleared benchmark with labelled answer spans and report
Recall@k, citation precision, grounded-answer accuracy, abstention precision,
and p50/p95 upload, retrieval, and answer latency. Evaluations should keep model
version, prompt revision, corpus hash, and environment configuration with each
result to make releases reproducible.

For a hosted release, Render logs now write safe timing records named
`citecanvas.upload` and `citecanvas.ask`. They include only page/source counts
and stage durations: preview rendering, native-text extraction, durable save,
fast retrieval, semantic retrieval, visual verification, and total elapsed
time. They intentionally exclude document text, filenames, questions, answers,
workspace IDs, and credentials. Compare one upload and one cited question before
and after deployment to obtain the production result for the selected Render
instance.

## VI. Issues Encountered and Resolutions

The initial local-only behavior could show previous sample files or fail after a
host restart. The resolution was explicit browser workspace scoping, content-hash
deduplication, R2 originals/pages, and Neon metadata. A second issue was broad
vector search: workspace and document payload filters plus payload indexes make
retrieval operate only within the active workspace. A third issue was unclear
failure diagnosis. Health checks, idempotent migrations, a production smoke
test, and opt-in telemetry now expose storage and service failures without
collecting document content.

The interface previously presented technical choices before a new visitor
understood the actions. Labels were simplified around user tasks and a
documentation page was added to explain the workflow and source evidence.

## VII. Limitations and Future Work

Anonymous session cookies are appropriate for a public demonstration but do not
provide named-user ownership, cross-device access, or organization-level access
control. A shared browser profile also shares its workspace by design. Large PDFs
and model processing remain bounded by the selected hosting, object-storage, and
model-provider limits. The current service should be protected by transport
security, production secrets, request-size limits, and provider rate limits in
the deployed environment.

Future work includes an independent benchmark corpus, asynchronous processing
for large uploads, collection-level retention reporting, performance dashboards
based on sanitized OpenTelemetry data, and optional authenticated workspaces for
users who require durable private ownership.

## VIII. Conclusion

CiteCanvas implements a concise, evidence-first PDF analysis workflow with no
login requirement. Its release architecture uses R2, PostgreSQL, Qdrant, NVIDIA,
Docker, Render, and optional OpenTelemetry to make the workflow recoverable,
browser-scoped, and deployable. Focused regression, storage-recovery,
containerization, migration, browser-isolation, and controlled RAG tests provide
release evidence while avoiding unnecessary model calls. Broader measured
evaluation remains future work.

## References

[1] Cloudflare, “S3 API compatibility,” *Cloudflare R2 Documentation*.
Available: https://developers.cloudflare.com/r2/get-started/s3/

[2] Qdrant, “Vector search and filtering,” *Qdrant Documentation*.
Available: https://qdrant.tech/documentation/search-patterns/vector-search-filtering/

[3] NVIDIA, “NVIDIA Embedding 2B API reference,” *NVIDIA API Documentation*.
Available: https://docs.api.nvidia.com/nim/reference/nvidia-embedding-2b-infer

[4] Render, “Blueprint specification,” *Render Documentation*.
Available: https://render.com/docs/blueprint-spec

[5] OpenTelemetry, “Exporters,” *OpenTelemetry Python Documentation*.
Available: https://opentelemetry.io/docs/languages/python/exporters/

[6] M. Faysse *et al*., “ColPali: Efficient Document Retrieval with Vision
Language Models,” *arXiv:2407.01449*, 2024. Available:
https://arxiv.org/abs/2407.01449

[7] “Cascaded Retrieval with Cross-Modal Query Refinement for Efficient Visual
Document Search,” *arXiv:2610.20367*, 2026. Available:
https://arxiv.org/abs/2610.20367
