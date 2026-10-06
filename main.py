"""Life OS backend. Run: uvicorn main:app --reload  ->  http://localhost:8000"""
import json, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.staticfiles import StaticFiles
import db, live

TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
PLAN_PROMPT = ('You are Life OS, a calm, practical problem solver. Turn the user problem into an action plan. '
  'Return ONLY JSON: {"title":"short title","summary":"one sentence","category":"Health|Money|Work|Home|Study|Relationships|Other",'
  '"tasks":[{"text":"concrete action","priority":"high|medium|low","hours":number hours from now until due}]}. '
  '4-8 tasks, ordered, small and doable.')

app = FastAPI(title="Life OS")

@app.get("/api/state")
def get_state():
    return db.load()

@app.put("/api/state")
async def put_state(req: Request):
    body = await req.json()
    db.save({"problems": body.get("problems", []), "chat": body.get("chat", {})})
    return {"ok": True}

@app.post("/api/plan")
async def make_plan(req: Request):
    text = str((await req.json()).get("text", "")).strip()[:4000]
    if not text:
        raise HTTPException(400, "text required")
    try:
        r = await live.get_client().aio.models.generate_content(
            model=TEXT_MODEL, contents=PLAN_PROMPT + "\n\nProblem: " + text,
            config={"response_mime_type": "application/json"})
        return json.loads(r.text)
    except Exception as e:
        raise HTTPException(502, f"Gemini error: {e}")

@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await ws.accept()
    try:
        await live.relay(ws)
    except Exception:
        pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass

app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
