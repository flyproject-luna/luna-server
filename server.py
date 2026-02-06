import os
import re
import json
import time
import uuid
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

APP_NAME = "luna-server"

# -----------------------------
# ENV
# -----------------------------
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()  # optional
LUNA_API_TOKEN = os.getenv("LUNA_API_TOKEN", "").strip()  # optional auth
TZ = os.getenv("TZ", "Europe/Tirane")

DB_PATH = os.getenv("DB_PATH", "luna.db")

# -----------------------------
# DB
# -----------------------------
def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alarms (
            id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            at_epoch INTEGER NOT NULL,
            city TEXT,
            message TEXT,
            created_epoch INTEGER NOT NULL,
            fired INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

init_db()

# -----------------------------
# Helpers
# -----------------------------
def now_local_str() -> str:
    # Simple local time without extra deps
    # Railway container TZ env works if set; otherwise UTC offset may vary.
    return datetime.now().strftime("%H:%M")

def norm_city(city: str) -> str:
    city = city.strip()
    city = re.sub(r"\s+", " ", city)
    # common fixes
    if city.lower() in ["tirane", "tiran", "tirana"]:
        return "Tirana"
    if city.lower() in ["londer", "london"]:
        return "London"
    return city

def require_auth(req: Request):
    if not LUNA_API_TOKEN:
        return
    auth = req.headers.get("Authorization", "")
    if auth != f"Bearer {LUNA_API_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")

def weather_now(city: str) -> Dict[str, Any]:
    if not OPENWEATHER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENWEATHER_API_KEY missing")

    city = norm_city(city)
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "sq",
    }
    r = requests.get(url, params=params, timeout=12)
    if r.status_code != 200:
        # pass through some debug
        try:
            j = r.json()
        except Exception:
            j = {"raw": r.text[:200]}
        raise HTTPException(status_code=502, detail={"weather_http": r.status_code, "weather_body": j})

    j = r.json()
    main = j.get("main", {})
    wind = j.get("wind", {})
    weather_arr = j.get("weather", [])
    desc = weather_arr[0].get("description", "") if weather_arr else ""
    temp = main.get("temp", None)
    feels = main.get("feels_like", None)
    hum = main.get("humidity", None)
    ws = wind.get("speed", None)

    return {
        "city": city,
        "desc": desc,
        "temp_c": temp,
        "feels_c": feels,
        "humidity": hum,
        "wind_ms": ws,
    }

def format_weather_sq(w: Dict[str, Any]) -> str:
    city = w["city"]
    desc = w["desc"] or "pa të dhëna"
    temp = w["temp_c"]
    feels = w["feels_c"]
    hum = w["humidity"]
    ws = w["wind_ms"]
    parts = [f"Moti në {city}: {desc}."]
    if temp is not None and feels is not None:
        parts.append(f"Temp {temp:.1f}°C (ndihet {feels:.1f}°C).")
    elif temp is not None:
        parts.append(f"Temp {temp:.1f}°C.")
    if hum is not None:
        parts.append(f"Lagështia {hum}%.")
    if ws is not None:
        parts.append(f"Era {ws:.2f} m/s.")
    return " ".join(parts)

# Optional LLM fallback (only if OPENAI_API_KEY exists)
def llm_answer(prompt: str) -> Optional[str]:
    if not OPENAI_API_KEY:
        return None
    # Use OpenAI Chat Completions via HTTPS (simple, no SDK)
    # NOTE: Keep key in ENV only.
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4.1-mini",
        "messages": [
            {"role": "system", "content": "Je Luna. Përgjigju shkurt, qartë, në shqip."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 180,
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=18)
        if r.status_code != 200:
            return None
        j = r.json()
        return j["choices"][0]["message"]["content"].strip()
    except Exception:
        return None

# -----------------------------
# Alarm logic
# -----------------------------
def create_alarm(device_id: str, at_epoch: int, city: str = "", message: str = "") -> str:
    alarm_id = str(uuid.uuid4())
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO alarms (id, device_id, at_epoch, city, message, created_epoch, fired) VALUES (?, ?, ?, ?, ?, ?, 0)",
        (alarm_id, device_id, int(at_epoch), city or "", message or "", int(time.time()))
    )
    conn.commit()
    conn.close()
    return alarm_id

def get_due_alarms(device_id: str, now_epoch: int) -> List[Dict[str, Any]]:
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM alarms WHERE device_id=? AND fired=0 AND at_epoch<=? ORDER BY at_epoch ASC",
        (device_id, int(now_epoch))
    )
    rows = cur.fetchall()
    ids = [r["id"] for r in rows]
    if ids:
        cur.execute(
            f"UPDATE alarms SET fired=1 WHERE id IN ({','.join(['?']*len(ids))})",
            ids
        )
        conn.commit()
    conn.close()
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "at_epoch": r["at_epoch"],
            "city": r["city"] or "",
            "message": r["message"] or "",
        })
    return out

# -----------------------------
# FastAPI
# -----------------------------
app = FastAPI(title=APP_NAME)

@app.get("/")
def root():
    return {"name": APP_NAME, "ok": True}

@app.get("/health")
def health():
    return {"ok": True, "name": APP_NAME}

@app.get("/ask")
def ask(q: str):
    text = (q or "").strip()
    if not text:
        return {"ok": False, "error": "empty query"}

    t = text.lower()

    # ora
    if "ora" in t and ("sa" in t or t == "ora" or "tani" in t):
        return {"ok": True, "answer": f"Ora tani është {now_local_str()}."}

    # moti: "moti ne tirane"
    m = re.search(r"moti\s+ne\s+(.+)$", t)
    if m:
        city_raw = m.group(1).strip()
        city = norm_city(city_raw)
        w = weather_now(city)
        return {"ok": True, "answer": format_weather_sq(w)}

    # fallback LLM if available
    ai = llm_answer(text)
    if ai:
        return {"ok": True, "answer": ai}

    # last fallback (no AI)
    return {"ok": True, "answer": "Jam gati. Pyet: 'ora' ose 'moti ne tirane'."}

@app.post("/alarm/set")
async def alarm_set(req: Request):
    """
    Body JSON:
    {
      "device_id":"esp32-001",
      "at_epoch": 1770392943,
      "city":"Tirana",
      "message":"Zgjohu dhe shkelqe sot"
    }
    """
    data = await req.json()
    device_id = str(data.get("device_id", "")).strip()
    at_epoch = data.get("at_epoch", None)
    city = str(data.get("city", "")).strip()
    message = str(data.get("message", "")).strip()

    if not device_id:
        raise HTTPException(status_code=400, detail="device_id missing")
    if at_epoch is None:
        raise HTTPException(status_code=400, detail="at_epoch missing")

    try:
        at_epoch = int(at_epoch)
    except Exception:
        raise HTTPException(status_code=400, detail="at_epoch invalid")

    alarm_id = create_alarm(device_id, at_epoch, city=city, message=message)
    return {"ok": True, "id": alarm_id}

@app.get("/alarm/due")
def alarm_due(device_id: str, now_epoch: Optional[int] = None):
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id missing")
    if now_epoch is None:
        now_epoch = int(time.time())
    due = get_due_alarms(device_id, int(now_epoch))
    return {"ok": True, "due": due}

@app.exception_handler(HTTPException)
def http_exc_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "error": exc.detail})
