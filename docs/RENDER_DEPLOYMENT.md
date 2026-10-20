# Deploy CiteCanvas on Render

## Create the service

1. In Render, select **New** then **Blueprint**.
2. Connect `pactaccount/CITECANVAS` on branch `main`.
3. Render reads `render.yaml`, builds the included Dockerfile, and checks
   `/api/health` before routing traffic.
4. Confirm the service name `citecanvas` and create the service.

The image runs versioned migrations before starting the server. A new version
is not routed until its health check succeeds.

## Add environment variables

Open the service **Environment** page. Use
[`.env.production.example`](../.env.production.example) as the checklist.
Add real values for `DATABASE_URL`; R2 bucket, endpoint, access key, and secret;
Qdrant URL and key; NVIDIA key; and optional OpenTelemetry endpoint and headers.

Keep `EVID_STORAGE_BACKEND=r2_neon`, `EVID_COOKIE_SECURE=true`, and
`EVID_WORKSPACE_TTL_HOURS=24`. Never put these real values in GitHub, a README,
browser JavaScript, or a public issue.

## First-release check

1. Open the Render URL in a normal browser window.
2. Upload one small PDF and open an original page.
3. Ask one focused question and confirm the citation page is correct.
4. Open a second tab: the document should be visible there.
5. Open a private/incognito window: it should begin empty.
6. Use **Settings - Clear this workspace** and confirm the document disappears.

Run this sequence once. It tests the full storage and RAG path without repeated
model calls.

## Updates and rollback

Push an approved commit to `main`. Render rebuilds the pinned Docker release
and executes migrations idempotently. If a new release fails `/api/health`, the
previous healthy release remains live. Use Render's **Rollback** action for a
functional regression discovered after deployment.
