import os
import time
import json
import re
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
import requests

# Optional: AI (nëse s'vendos OPENAI_API_KEY, bie në mode "pa AI")
try:
    from openai import OpenAI
    _openai_ok = True
except Exception:
    _openai_ok = False

app = FastAPI()

OPENWEATHER_KEY = os.getenv("OPENWEATHER_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

client = OpenAI(api_key=OPENAI_API_KEY) if (_openai_ok and OPENAI_API_KEY) else None

# --- in-memory store (OK për test / MVP). Për prodhim serioz: DB (Redis/Postgres) ---
# alarms: list of dicts: {id, device_id, epoch, city, label}
ALARMS: List[Dict[str, Any]] = []

def now_epoch() -> int:
    return int(time.time())

def normalize_city(city: str) -> str:
    c = (city or "").strip().lower()
    fix = {
        "tirane": "Tirana,AL",
        "tirana": "Tirana,AL",
        "londer": "London,GB",
        "london": "London,GB",
    }
    return fix.get(c, city)

def get_weather_text(city: str) -> str:
    if not OPENWEATHER_KEY:
        return "S’kam OPENWEATHER_API_KEY të vendosur."
    q = normalize_city(city)
    url = "https://api.openweathermap.org/data/2.5/weather"
    r = requests.get(url, params={"q": q, "appid": OPENWEATHER_KEY, "units": "metric", "lang": "sq"}, timeout=10)
    if r.status_code != 200:
        return f"S’e gjeta motin për {city}."
    d = r.json()
    temp = round(d["main"]["temp"])
    desc = d["weather"][0]["description"]
    return f"Koha është {desc} dhe temperatura është {temp}°C në {city}."

def ai_answer_al(q: str) -> str:
    # nëse s’ka OpenAI key → fallback
    if not client:
        return f"Luna (pa AI): e mora pyetjen '{q}'."
    sys = (
        "Ti je Luna. Përgjigju në shqip, shkurt, fiks, pa llafe kot. "
        "Nëse pyetja kërkon informacion të freskët, thuaj që duhen burime web dhe kthe një përgjigje të arsyeshme."
    )
    resp = client.responses.create(
        model=OPENAI_MODEL,
        instructions=sys,
        input=q,
    )
    text = ""
    for item in resp.output:
        if item.type == "message":
            for c in item.content:
                if c.type == "output_text":
                    text += c.text
    text = re.sub(r"\s+", " ", text).strip()
    return text[:800]

class AlarmSet(BaseModel):
    device_id: str
    epoch: int  # unix seconds (ESP32 e llogarit pasi ka NTP)
    city: str = "Tiranë"
    label: str = "Alarm"

@app.get("/")
def root():
    return {"ok": True, "status": "LUNA server online", "time": now_epoch()}

@app.get("/ask")
def ask(q: str = Query(...), device_id: str = Query("demo")):
    q2 = (q or "").strip()
    if not q2:
        raise HTTPException(400, "missing q")

    ql = q2.lower()

    # komandë: ora
    if ql in ["ora", "sa eshte ora", "sa eshte ora tani"]:
        return {"ok": True, "answer": "Ora merret nga pajisja (ESP32) pasi ka NTP."}

    # komandë: moti ne <qytet>
    m = re.search(r"\bmoti\s+(ne|në)\s+(.+)$", ql)
    if m:
        city = m.group(2).strip()
        return {"ok": True, "answer": get_weather_text(city)}

    # komandë: vendos alarm (p.sh “vendos alarm pas 10 minutash” – version i thjeshtë)
    if "alarm" in ql and ("vendos" in ql or "set" in ql):
        return {"ok": True, "answer": "Përdor /alarm/set nga app/ESP32: jep epoch."}

    # fallback: AI
    return {"ok": True, "answer": ai_answer_al(q2)}

@app.post("/alarm/set")
def alarm_set(a: AlarmSet):
    # ruaj alarm
    alarm_id = f"a{len(ALARMS)+1}_{int(time.time())}"
    ALARMS.append({
        "id": alarm_id,
        "device_id": a.device_id,
        "epoch": int(a.epoch),
        "city": a.city,
        "label": a.label
    })
    return {"ok": True, "id": alarm_id}

@app.get("/alarm/next")
def alarm_next(device_id: str):
    now = now_epoch()
    future = [x for x in ALARMS if x["device_id"] == device_id and x["epoch"] >= now]
    future.sort(key=lambda x: x["epoch"])
    if not future:
        return {"ok": True, "next": None}
    return {"ok": True, "next": future[0]}

@app.get("/alarm/pop")
def alarm_pop(device_id: str):
    """ESP32 e thërret shpesh. Nëse ka alarm që ka ardhur koha, ia kthen 1 herë dhe e heq."""
    now = now_epoch()
    due = [x for x in ALARMS if x["device_id"] == device_id and x["epoch"] <= now]
    due.sort(key=lambda x: x["epoch"])
    if not due:
        return {"ok": True, "alarm": None}

    alarm = due[0]
    # remove it
    ALARMS.remove(alarm)

    # build spoken message
    weather = get_weather_text(alarm.get("city", "Tiranë"))
    msg = f"Zgjohu dhe shkëlqe sot. {weather}"
    return {"ok": True, "alarm": alarm, "message": msg}
