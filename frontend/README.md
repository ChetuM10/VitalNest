# VitalNest frontend (T12)

React, TypeScript and Tailwind (v4), built with Vite. Design: "Powder & Ink", light and dark themes. Fonts (Atkinson Hyperlegible, DM Mono) are self-hosted through `@fontsource`, so no request goes to a font server.

## Run it against the real backend

Two terminals, from the repository root (or use the two entries in `.claude/launch.json`):

```bash
.venv/Scripts/python -m uvicorn app.local:app --app-dir backend --port 8000   # API; reads keys from ingestion/.env
npm --prefix frontend run dev                                                   # http://localhost:5173
```

The dev server proxies `/v1` to the API and adds a fake user identity header, so local development works without signing in (the local API accepts it only because `app/local.py` sets `LOCAL_DEV_AUTH=1`). That setting lives only in `vite.config.ts`; it is not in a production build, and a deployed API ignores the header. A real question makes real Pinecone and Claude calls (a fraction of a cent each).

## Commands

```bash
npm --prefix frontend test         # 117 tests (stream reader, limits, safe markdown, contrast in both themes, components)
npm --prefix frontend run build    # type-check, then build to frontend/dist
```

## Settings

- `VITE_API_BASE_URL`: base URL of the API in a deployed build (empty = same origin).
- `VITE_HIDE_DEMO=true`: removes the "Demo states" switch for a release build.
- `VITE_COGNITO_DOMAIN`, `VITE_COGNITO_CLIENT_ID`: the Cognito Hosted UI address and app client id (public values; see `.env.example`). Without them sign-in is off.

## Notes

- Sign-in uses the Cognito Hosted UI with PKCE (`src/lib/auth/cognito.ts`); the access token is sent as a Bearer header by `getAuthHeaders()` in `src/lib/api/sse.ts`. Signed-out visitors are asked to sign in and nothing is sent.
- Answers are markdown. `src/lib/markdown.tsx` renders only paragraphs, bullet lists and bold, as React elements (never raw HTML); links are opened only if they are `https`.
- Follow-up questions are Perplexity-style rows (corner arrow, divider lines), not chips.
- The project folder is inside OneDrive: `frontend/node_modules` has thousands of files that would sync. Consider excluding that folder from OneDrive sync.
