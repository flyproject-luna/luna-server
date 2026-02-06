import os
import time
import uuid
import sqlite3
from typing import Optional, List, Dict, Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

APP_NAME = "luna-server"

DB_PATH = os.getenv("DB_PATH", "luna.db")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()

app = FastAPI(title=APP_NAME)

# ---------- DB ----------
def db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alarms (
            id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            at_epoch INTEGER NOT NULL,
            city TEXT DEFAULT '',
            message TEXT DEFAULT '',
            created_at INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------- Models ----------
class AskIn(BaseModel):
    device_id: str = Field(default="unknown")
    text: str = Field(min_length=1, max_length=500)
    city: Optional[str] = ""

class AskOut(BaseModel):
    ok: bool
    answer: str

class AlarmSetIn(BaseModel):
    device_id: str
    at_epoch: int
    city: Optional[str] = ""
    message: Optional[str] = ""

class AlarmOut(BaseModel):
    ok: bool
    id: str

class AlarmRow(BaseModel):
    id: str
    device_id: str
    at_epoch: int
    city: str
    message: str

class AlarmListOut(BaseModel):
    ok: bool
    alarms: List[AlarmRow]

class AlarmDeleteIn(BaseModel):
    device_id: str
    id: str

# ---------- Helpers ----------
def now_epoch() -> int:
    return int(time.time())

def normalize_text(s: str) -> str:
    return " ".join((s or "").strip().split())

def weather_for_city(city: str) -> Optional[str]:
    city = normalize_text(city)
    if not city:
        return None
    if not OPENWEATHER_API_KEY:
        return "Weather key missing on server (OPENWEATHER_API_KEY)."
    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"},
            timeout=10,
        )
        if r.status_code != 200:
            return f"Can't get weather for '{city}' (status {r.status_code})."
        j = r.json()
        temp = j["main"]["temp"]
        desc = j["weather"][0]["description"]
        hum = j["main"].get("humidity")
        wind = j.get("wind", {}).get("speed")
        return f"Weather in {city}: {temp:.1f}°C, {desc}. Humidity {hum}%, wind {wind} m/s."
    except Exception as e:
        return f"Weather error: {e}"

def smart_reply(text: str, city: str) -> str:
    t = normalize_text(text).lower()

    # super bazë, por stabile (pa LLM key)
    if "hi" in t or "hey" in t or "pershendetje" in t or "tung" in t:
        return "Tung vlla. Jam gati."

    if "time" in t or "ora" in t:
        return f"Ora (epoch) eshte: {now_epoch()}"

    if "weather" in t or "mot" in t:
        w = weather_for_city(city) if city else "Shkruaj edhe qytetin (city)."
        return w

    if "alarm" in t and ("list" in t or "shfaq" in t):
        return "Per alarmet perdor endpoint: /alarm/list (device_id)."

    if "help" in t or "ndihme" in t:
        return (
            "Komanda: "
            "POST /ask {device_id,text,city} | "
            "POST /alarm/set {device_id,at_epoch,city,message} | "
            "GET /alarm/list?device_id=... | "
            "POST /alarm/delete {device_id,id} | "
            "GET /weather?city=..."
        )

    # fallback
    return "E mora. Shkruaj me sakte: (mot/ora/alarm/help)."

# ---------- Routes ----------
@app.get("/", response_class=PlainTextResponse)
def root():
    return "OK - luna-server"

@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"

@app.post("/ask", response_model=AskOut)
def ask(payload: AskIn):
    answer = smart_reply(payload.text, payload.city or "")
    return AskOut(ok=True, answer=answer)

@app.get("/weather", response_class=PlainTextResponse)
def weather(city: str):
    return weather_for_city(city) or "Missing city"

@app.post("/alarm/set", response_model=AlarmOut)
def alarm_set(payload: AlarmSetIn):
    if payload.at_epoch < now_epoch() - 10:
        raise HTTPException(status_code=400, detail="at_epoch is in the past")
    alarm_id = str(uuid.uuid4())
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO alarms (id, device_id, at_epoch, city, message, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (alarm_id, payload.device_id, int(payload.at_epoch), payload.city or "", payload.message or "", now_epoch()),
    )
    conn.commit()
    conn.close()
    return AlarmOut(ok=True, id=alarm_id)

@app.get("/alarm/list", response_model=AlarmListOut)
def alarm_list(device_id: str):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, device_id, at_epoch, city, message FROM alarms WHERE device_id=? ORDER BY at_epoch ASC",
        (device_id,),
    )
    rows = [AlarmRow(**dict(r)) for r in cur.fetchall()]
    conn.close()
    return AlarmListOut(ok=True, alarms=rows)

@app.post("/alarm/delete", response_class=PlainTextResponse)
def alarm_delete(payload: AlarmDeleteIn):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM alarms WHERE id=? AND device_id=?", (payload.id, payload.device_id))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    if deleted == 0:
        raise HTTPException(status_code=404, detail="not found")
    return "ok"

@app.get("/alarm/next", response_class=PlainTextResponse)
def alarm_next(device_id: str):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, at_epoch, city, message FROM alarms WHERE device_id=? AND at_epoch>=? ORDER BY at_epoch ASC LIMIT 1",
        (device_id, now_epoch()),
    )
    r = cur.fetchone()
    conn.close()
    if not r:
        return ""
    # format: id|epoch|city|message
    return f"{r['id']}|{r['at_epoch']}|{r['city']}|{r['message']}"
