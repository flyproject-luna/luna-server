import os
import time
import re
import sqlite3
from typing import Optional, Dict, Any

import httpx
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel

APP_NAME = "luna-server"
DB_PATH = os.getenv("DB_PATH", "luna.db")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()

app = FastAPI(title=APP_NAME)

# -------------------- DB --------------------
def db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS alarms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL,
        at_epoch INTEGER NOT NULL,
        city TEXT DEFAULT 'Tirane',
        message TEXT DEFAULT '',
        created_at INTEGER NOT NULL,
        fired INTEGER DEFAULT 0
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_alarms_device_time ON alarms(device_id, at_epoch)")
    con.commit()
    con.close()

init_db()

# -------------------- Models --------------------
class AlarmSetReq(BaseModel):
    device_id: str
    at_epoch: int
    city: Optional[str] = "Tirane"
    message: Optional[str] = ""

# -------------------- Helpers --------------------
def now_epoch() -> int:
    return int(time.time())

def norm_city(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

async def fetch_weather(city: str) -> Dict[str, Any]:
    if not OPENWEATHER_API_KEY:
        return {"ok": False, "error": "OPENWEATHER_API_KEY missing"}

    city = norm_city(city)
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "sq"
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, params=params)
        if r.status_code != 200:
            try:
                j = r.json()
            except Exception:
                j = {"message": r.text[:200]}
            return {"ok": False, "error": f"weather error {r.status_code}: {j}"}

        j = r.json()
        desc = (j.get("weather") or [{}])[0].get("description", "")
        temp = j.get("main", {}).get("temp")
        feels = j.get("main", {}).get("feels_like")
        hum = j.get("main", {}).get("humidity")
        wind = j.get("wind", {}).get("speed")
        return {
            "ok": True,
            "city": city,
            "desc": desc,
            "temp_c": temp,
            "feels_c": feels,
            "humidity": hum,
            "wind_ms": wind
        }

def format_weather_simplified(w: Dict[str, Any]) -> str:
    if not w.get("ok"):
        return f"S’munda ta marr motin. {w.get('error','')}"
    desc = w.get("desc", "")
    temp = w.get("temp_c", "?")
    feels = w.get("feels_c", "?")
    hum = w.get("humidity", "?")
    wind = w.get("wind_ms", "?")
    return f"Moti ne {w.get('city')}: {desc}. Temp {temp}°C (ndihet {feels}°C). Lageshtia {hum}%. Era {wind} m/s."

# -------------------- Routes --------------------
@app.get("/")
def root():
    return {"status": "Luna server online", "service": APP_NAME, "time": now_epoch()}

@app.get("/health")
def health():
    return {"ok": True, "service": APP_NAME, "time": now_epoch()}

@app.get("/ask")
async def ask(q: str = Query(..., min_length=1)):
    text = q.strip().lower()

    # ora
    if text in ["ora", "sa eshte ora", "time"]:
        t = time.localtime()
        return {"ok": True, "answer": f"Ora tani eshte {t.tm_hour:02d}:{t.tm_min:02d}."}

    # moti ne <qytet>
    m = re.search(r"moti\s+ne\s+(.+)$", text)
    if m:
        city = norm_city(m.group(1))
        w = await fetch_weather(city)
        return {"ok": True if w.get("ok") else False, "answer": format_weather_simplified(w), **({"weather": w} if w.get("ok") else {"error": w.get("error")})}

    # barcaleta (si ne screenshot)
    if "barcalet" in text or "barcaleta" in text:
        return {"ok": True, "answer": "Pse kompjuteri s’qeshi? Se kishte shume tabs hapur."}

    # fallback
    return {"ok": True, "answer": "Me thuaj: 'ora' ose 'moti ne Tirane' ose vendos nje alarm."}

@app.post("/alarm/set")
def alarm_set(req: AlarmSetReq):
    if req.at_epoch < 1000000000:
        raise HTTPException(status_code=400, detail="at_epoch duhet te jete UNIX epoch (sekonda).")

    con = db()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO alarms(device_id, at_epoch, city, message, created_at, fired) VALUES (?,?,?,?,?,0)",
        (req.device_id.strip(), int(req.at_epoch), (req.city or "Tirane").strip(), (req.message or "").strip(), now_epoch())
    )
    con.commit()
    alarm_id = cur.lastrowid
    con.close()
    return {"ok": True, "alarm_id": alarm_id}

@app.get("/alarm/next")
def alarm_next(device_id: str, grace_sec: int = 30):
    """
    ESP32 e thirr kete endpoint çdo pak sekonda.
    Kthen alarm nese eshte koha (now >= at_epoch) dhe s'eshte fired.
    grace_sec = sa sekonda lejojme vonese pa e humbur alarmin.
    """
    device_id = device_id.strip()
    now = now_epoch()
    con = db()
    cur = con.cursor()

    # gjej alarmin me te afert qe eshte "due"
    cur.execute(
        """
        SELECT * FROM alarms
        WHERE device_id = ? AND fired = 0 AND at_epoch <= ? AND at_epoch >= ?
        ORDER BY at_epoch ASC
        LIMIT 1
        """,
        (device_id, now, now - abs(int(grace_sec)))
    )
    row = cur.fetchone()
    if not row:
        con.close()
        return {"ok": True, "due": False}

    # sheno fired qe mos perseritet
    cur.execute("UPDATE alarms SET fired = 1 WHERE id = ?", (row["id"],))
    con.commit()
    con.close()

    return {
        "ok": True,
        "due": True,
        "alarm": {
            "id": row["id"],
            "device_id": row["device_id"],
            "at_epoch": row["at_epoch"],
            "city": row["city"],
            "message": row["message"]
        }
    }

@app.get("/weather")
async def weather(city: str = "Tirane"):
    w = await fetch_weather(city)
    if not w.get("ok"):
        return {"ok": False, "error": w.get("error")}
    return {"ok": True, "weather": w, "text": format_weather_simplified(w)}
