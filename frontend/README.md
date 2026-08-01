# Trade Discipline — React dashboard

Replaces the Streamlit UI. The Python backend (`agents/`, `backend/`,
`app.py`) is untouched — this talks to it through one new thin adapter,
`server.py`, at the project root.

## Run it

**1. Backend API** (from the Python project root, same env as before):
```bash
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

**2. Frontend** (from this `frontend/` folder):
```bash
npm install
npm run dev
```
Open the printed localhost URL. In dev, Vite proxies `/api/*` to
`http://localhost:8000` (see `vite.config.js`).

**Production build:** `npm run build` outputs static files to `dist/` —
serve them with any static host, with the FastAPI process running
alongside for `/api`.

## Why this fixes the "goes to sleep" problem

Streamlit Community Cloud suspends an app after a period of no viewer
traffic, taking the in-process poller thread down with it. Serving a
static React build separately from the API process means the API can run
on infrastructure that doesn't idle-sleep (or can be kept warm/health-
checked independently of whether anyone has a browser tab open), and the
UI itself is a static bundle with no server-side session to lose.

## What's new vs. what's unchanged

- **New:** `server.py` (FastAPI adapter, same functions `app.py` called),
  `frontend/` (this React app).
- **Unchanged:** `agents/`, `backend/`, `prompts/`, `app.py` (kept as a
  reference / fallback UI), tests.
