# Life OS: Python backend + Gemini Live
## Entire App made with Claudecode and Wisperflow
```bash
cd lifeos
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # add your GEMINI_API_KEY from https://aistudio.google.com/apikey
uvicorn main:app --reload
```
Open http://localhost:8000 (mic access works on localhost or HTTPS only). Use headphones to avoid echo.

- `main.py` REST (`/api/state`, `/api/plan`) + WebSocket `/ws/live` + serves `static/`
- `live.py` relays the browser to `gemini-3.1-flash-live-preview` (audio in 16 kHz PCM, audio out 24 kHz), with tools `add_task` / `complete_task` that edit your plan
- `db.py` SQLite storage (`lifeos.db`) with resilient data loading for legacy or partially broken state files
- `static/index.html` now supports adding manual tasks and exporting a plan as JSON from the dashboard

Before deploying: this is single-user with no login, so add authentication, an origin check on the WebSocket and rate limits, otherwise anyone who finds it can spend your API key.

## VS Code quick start
1. File > Open Folder... and choose this `lifeos` folder.
2. Terminal > Run Task > **Setup (create venv + install)** (once).
3. Copy `.env.example` to `.env` and add your `GEMINI_API_KEY`.
4. Press **F5** (Life OS: run server) or run the task **Run Life OS**, then open http://localhost:8000.
