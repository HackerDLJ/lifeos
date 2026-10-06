"""Relays the browser <-> Gemini Live API (gemini-3.1-flash-live-preview).
The API key stays on the server. Browser protocol (JSON over WebSocket):
  client -> {type:start,active} | {type:audio,data(b64 pcm16),rate} | {type:audio_end} | {type:text,text}
  server -> {type:audio,data} | {type:transcript,role,text} | {type:interrupted}
            | {type:turn_complete} | {type:state,state} | {type:error,message}
"""
import asyncio, base64, os, time, uuid
from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types
import db

MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
_client = None

def get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client

TOOLS = [{"function_declarations": [
    {"name": "add_task", "description": "Add a task to the user's active plan.",
     "parameters": {"type": "object", "properties": {
         "text": {"type": "string"},
         "priority": {"type": "string", "enum": ["high", "medium", "low"]},
         "hours": {"type": "number", "description": "Hours from now until due"}},
         "required": ["text"]}},
    {"name": "complete_task", "description": "Mark a task done (or not done) by matching part of its text.",
     "parameters": {"type": "object", "properties": {
         "task_text": {"type": "string"}, "done": {"type": "boolean"}},
         "required": ["task_text"]}},
]}]

def _plan(state, pid):
    return next((p for p in state["problems"] if p["id"] == pid), None)

def _summary(p):
    return "\n".join(f"- [{'x' if t['done'] else ' '}] {t['text']} ({t['priority']})" for t in p["tasks"])

def run_tool(pid, name, args):
    state = db.load()
    p = _plan(state, pid)
    if not p:
        return {"error": "no active plan"}, None
    if name == "add_task":
        pr = args.get("priority")
        p["tasks"].append({"id": uuid.uuid4().hex[:7], "text": str(args["text"])[:300],
            "priority": pr if pr in ("high", "medium", "low") else "medium",
            "due": int((time.time() + float(args.get("hours", 24)) * 3600) * 1000), "done": False})
    elif name == "complete_task":
        q = str(args["task_text"]).lower()
        t = next((t for t in p["tasks"] if q in t["text"].lower()), None)
        if not t:
            return {"error": "no matching task"}, None
        t["done"] = bool(args.get("done", True))
    else:
        return {"error": "unknown tool"}, None
    db.save(state)
    return {"ok": True, "plan": _summary(p)}, state

async def relay(ws: WebSocket):
    start = await ws.receive_json()
    pid = start.get("active")
    p = _plan(db.load(), pid)
    system = ("You are Life OS, a calm, warm, practical coach. Speak briefly (under 40 words) and "
              "give concrete next steps. Use add_task / complete_task when the user asks to change the plan.")
    if p:
        system += f"\n\nActive plan: {p['title']} - {p['summary']}\n{_summary(p)}"
    config = {"response_modalities": ["AUDIO"], "system_instruction": system,
              "input_audio_transcription": {}, "output_audio_transcription": {}, "tools": TOOLS}

    async with get_client().aio.live.connect(model=MODEL, config=config) as s:
        async def up():
            while True:
                m = await ws.receive_json()
                t = m.get("type")
                if t == "audio":
                    rate = int(m.get("rate", 16000))
                    await s.send_realtime_input(audio=types.Blob(
                        data=base64.b64decode(m["data"]), mime_type=f"audio/pcm;rate={rate}"))
                elif t == "audio_end":
                    await s.send_realtime_input(audio_stream_end=True)
                elif t == "text":
                    await s.send_realtime_input(text=str(m["text"])[:2000])

        async def down():
            while True:
                async for r in s.receive():
                    if r.tool_call:
                        out = []
                        for fc in r.tool_call.function_calls:
                            res, state = run_tool(pid, fc.name, dict(fc.args or {}))
                            out.append(types.FunctionResponse(id=fc.id, name=fc.name, response=res))
                            if state:
                                await ws.send_json({"type": "state", "state": state})
                        await s.send_tool_response(function_responses=out)
                    sc = r.server_content
                    if not sc:
                        continue
                    if sc.model_turn:
                        for part in sc.model_turn.parts or []:
                            if part.inline_data and part.inline_data.data:
                                await ws.send_json({"type": "audio",
                                    "data": base64.b64encode(part.inline_data.data).decode()})
                    if sc.input_transcription and sc.input_transcription.text:
                        await ws.send_json({"type": "transcript", "role": "user", "text": sc.input_transcription.text})
                    if sc.output_transcription and sc.output_transcription.text:
                        await ws.send_json({"type": "transcript", "role": "model", "text": sc.output_transcription.text})
                    if sc.interrupted:
                        await ws.send_json({"type": "interrupted"})
                    if sc.turn_complete:
                        await ws.send_json({"type": "turn_complete"})

        tasks = [asyncio.create_task(up()), asyncio.create_task(down())]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        for t in done:
            exc = t.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                try:
                    await ws.send_json({"type": "error", "message": f"Live session ended: {exc}"})
                except Exception:
                    pass
