# VitalNest

VitalNest is an AI assistant that answers general health questions using trusted public sources, and shows
exactly where each answer came from.

> **Not medical advice.** VitalNest shares general health information only. It is not a doctor, does not
> diagnose, and is not a substitute for professional care. In an emergency, call your local emergency number.

## What it does

- Answers health questions from **MedlinePlus, the CDC and the WHO**, with source cards linking to the pages used.
- Streams the answer live, then suggests follow-up questions.
- Remembers the conversation, so follow-ups like "what about children?" make sense.
- Says "I don't have enough information" instead of guessing when the sources don't cover a question.
- Spots emergencies, self-harm and unsafe requests first and gives a safe, fixed reply instead of an AI answer.
- Asks a short question when someone says they feel unwell without saying what is wrong.
- Fixes common typos ("diabtes") and replies kindly to greetings and thanks.

## How it works

```
Question -> safety check -> keyword search (BM25) + meaning search (Pinecone)
         -> merge results (RRF) -> Claude writes a grounded answer
         -> each sentence is safety-checked as it streams -> sources and follow-ups
```

| Part     | Technology                                                                                                             |
| -------- | ---------------------------------------------------------------------------------------------------------------------- |
| Frontend | React 19, TypeScript, Tailwind CSS 4, Vite                                                                             |
| Backend  | Python, FastAPI, Pydantic                                                                                              |
| Search   | BM25 (`rank-bm25`) and Pinecone (`multilingual-e5-large`, cosine, 1024 dimensions), merged with Reciprocal Rank Fusion |
| AI       | Anthropic Claude (Haiku 5.5 by default)                                                                                |
| Sign-in  | Amazon Cognito (the API verifies the token itself)                                                                     |
| Hosting  | Render (API) and Vercel (website)                                                                                      |

## Project layout

| Folder        | What is in it                                                                                     |
| ------------- | ------------------------------------------------------------------------------------------------- |
| `backend/`    | The FastAPI app: chat, search, safety, sign-in, rate limits, and tests                            |
| `frontend/`   | The website: chat card, source cards, follow-ups, light and dark themes, and tests                |
| `ingestion/`  | Offline script that downloads the sources, cleans and chunks them, and builds the search indexes  |
| `evaluation/` | Test questions and scripts that measure search quality and check that answers match their sources |
| `render.yaml` | Render setup for the API                                                                          |

## Limits and safety

- Messages are limited to 500 characters, 20 history messages and 8,000 characters in total.
- Each user is limited to 6 questions a minute and 60 a day, with an overall daily cap to control cost.
- Answers are shown as safe text only (no raw HTML), and links open only if they are `https`.
- Keys are never stored in the repo. Only `.env.example` files with placeholders are committed.

## Run it locally

You need Python 3.14, Node.js, a [Pinecone](https://www.pinecone.io/) key and an
[Anthropic](https://www.anthropic.com/) key.

```bash
# 1. Python environment
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements-dev.txt -r ingestion/requirements.txt

# 2. Keys: copy ingestion/.env.example to ingestion/.env and fill in your keys (git-ignored)

# 3. Build the knowledge base once (see ingestion/README.md for the full steps)
cd ingestion
../.venv/Scripts/python -m vitalnest_ingest fetch
../.venv/Scripts/python -m vitalnest_ingest build --input data/raw/<file>.xml
../.venv/Scripts/python create_index.py
../.venv/Scripts/python -m vitalnest_ingest upload
cd ..

# 4. Start the API and the website (two terminals, from the project root)
.venv/Scripts/python -m uvicorn app.local:app --app-dir backend --port 8000
npm --prefix frontend install
npm --prefix frontend run dev        # http://localhost:5173
```

A real question makes real Pinecone and Claude calls, which cost a fraction of a cent each.
On macOS or Linux use `.venv/bin/python` instead of `.venv/Scripts/python`.

## Tests

```bash
cd backend && ../.venv/Scripts/python -m pytest      # backend (live tests are skipped by default)
npm --prefix frontend test                           # frontend
cd evaluation && ../.venv/Scripts/python retrieval_eval.py   # search quality (needs the Pinecone key)
```

## Search quality

On the evaluation set, Pinecone found the right page in the top 3 results for every answerable question. The
"not enough information" cutoff (0.845) comes from the gap between answerable and unanswerable questions: it
wrongly refused none of the 15 answerable ones and wrongly answered none of the 10 unanswerable ones. Reports are in
`evaluation/results/`.

## Deploying

The API runs on Render (the setup is in `render.yaml`) and the website on Vercel. Enter these in each dashboard,
never in the repo:

- **Render:** `PINECONE_API_KEY`, `ANTHROPIC_API_KEY`, `ALLOWED_ORIGIN` (your Vercel address),
  `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`
- **Vercel** (root folder `frontend`): `VITE_API_BASE_URL`, `VITE_COGNITO_DOMAIN`, `VITE_COGNITO_CLIENT_ID`,
  and `VITE_HIDE_DEMO=true` to hide the demo switch
- **Cognito:** add your Vercel address, with a trailing slash, to the allowed callback and sign-out URLs

## Sources and attribution

Health content comes from [MedlinePlus](https://medlineplus.gov/) (U.S. National Library of Medicine),
the [CDC](https://www.cdc.gov/) and the [WHO](https://www.who.int/). WHO content is under CC BY-NC-SA 3.0 IGO
(non-commercial, attribution, share-alike). Every answer links back to the pages it used.
