# Deploying VitalNest (Render + Vercel + Cognito)

Free tiers only. Do the steps in order. Nothing here needs a credit card except Claude credits (already prepaid).

## 0. Before you start

- Commit and push the repository to GitHub (the owner does this). It must include `render.yaml` and
  `backend/app/data/bm25_index.json` (17 MB, the keyword index the API loads at start-up).
- Keys stay out of GitHub: `.env` files are ignored. You will paste the two keys into Render's dashboard.

## 1. Backend on Render

1. Render dashboard > **New > Blueprint** > pick the GitHub repository. Render reads `render.yaml`
   (service `vitalnest-api`, free plan, root folder `backend`).
2. When asked for the values marked "sync: false", enter:
   - `PINECONE_API_KEY` (your current key) and `ANTHROPIC_API_KEY`
   - `COGNITO_USER_POOL_ID` and `COGNITO_CLIENT_ID` (from your Cognito user pool and app client)
   - `ALLOWED_ORIGIN`: the exact Vercel address, e.g. `https://vitalnest.vercel.app` (no trailing slash).
     If you do not know it yet, put a placeholder and change it after step 2.
3. Deploy. The build installs `backend/requirements.txt`; the start command is
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT`; Render checks `/v1/health`.
4. Open `https://<your-service>.onrender.com/v1/health`: it should show `{"status":"ok", ...}`.
   Free services sleep after 15 minutes without traffic; the first request afterwards takes about a minute
   (the chat page shows a "waking up" note after 6 seconds).
5. If the build fails on the Python version, change `PYTHON_VERSION` in the service's Environment tab
   (the repo is tested on 3.14).

## 2. Frontend on Vercel

1. Vercel > **Add New > Project** > the same repository. Settings:
   - Root Directory: `frontend`
   - Framework: Vite (build `npm run build`, output `dist`)
2. Environment variables (Production):
   - `VITE_API_BASE_URL` = the Render address (no trailing slash)
   - `VITE_COGNITO_DOMAIN` = your Hosted UI address, `https://<your-domain-prefix>.auth.<region>.amazoncognito.com`
   - `VITE_COGNITO_CLIENT_ID` = your app client ID (Cognito > User pool > App integration)
   - `VITE_HIDE_DEMO` = `true`
3. Deploy, then copy the Vercel address.

## 3. Connect the pieces

1. **Render:** set `ALLOWED_ORIGIN` to the Vercel address (Environment tab), save (it redeploys).
2. **Cognito** (User pool > App integration > App client > Hosted UI): add the Vercel address **with a trailing
   slash** (e.g. `https://vitalnest.vercel.app/`) to both **Allowed callback URLs** and **Allowed sign-out URLs**.
   Keep `http://localhost:5173/` for local work.
3. Open the Vercel site, sign in, ask a question. Expected: sources from MedlinePlus, WHO or the CDC.

## 4. If something is wrong

| Symptom | Likely cause |
|---|---|
| Browser console shows a CORS error | `ALLOWED_ORIGIN` on Render does not exactly match the Vercel address |
| Cognito says `redirect_mismatch` | the Vercel address (with trailing slash) is missing from the callback URLs |
| Sign-in works but chat says "Please sign in" | `COGNITO_*` on Render differ from the pool/client, or the token expired (sign in again) |
| Chat returns 503 | a key is missing on Render (`PINECONE_API_KEY` or `ANTHROPIC_API_KEY`) |
| Answers say "not enough information" for everything | the keyword index or Pinecone data is missing; check the Render logs and `ingestion/check_pinecone.py` |
| First answer is very slow | the free service was asleep; wait about a minute |

## 5. After changing sources

Re-run ingestion and the evaluation (see `ingestion/README.md` and `evaluation/README.md`), copy the new
`bm25_index.json` into `backend/app/data/`, commit, and push; Render redeploys.
