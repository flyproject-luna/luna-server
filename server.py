import os
import time
from typing import Optional, Dict, Any

import requests
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

app = FastAPI(title="luna-server")

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()

# Alarm storage (simple in-memory).
# NOTE: On Railway/Fly kjo humbet në restart. Për prodhim, kalo në DB (Redis/Postgres).
ALARMS: Dict[str, Dict[str, Any]] = {}
# structure:
# ALARMS[device_id] = {"at_epoch": int, "city": str, "message": str, "fired": bool}

def now_epoch() -> int:
    return int(time.time())

def ok(answer: str):
    return JSONResponse({"ok": True, "answer": answer})

def bad(msg: str, status: int = 400):
    return JSONResponse({"ok": False, "error": msg}, status_code=status)

@app.get("/")
def root():
    return ok("Luna server online. Use /health, /ask, /alarm/set, /alarm/next")

@app.get("/health")
def health():
    return {"ok": True, "service": "luna-server", "ts": now_epoch()}

def weather_text(city: str) -> str:
    if not OPENWEATHER_API_KEY:
        raise RuntimeError("OPENWEATHER_API_KEY missing")

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric", "lang": "sq"}
    r = requests.get(url, params=params, timeout=10)
    data = r.json()

    if r.status_code != 200:
        # OpenWeather shpesh jep 404 city not found
        msg = data.get("message", "weather error")
        raise RuntimeError(f"Weather error {r.status_code}: {msg}")

    main = data["main"]
    wind = data.get("wind", {})
    clouds = data.get("clouds", {})
    weather_arr = data.get("weather", [])
    desc = weather_arr[0].get("description", "") if weather_arr else ""

    temp = float(main.get("temp", 0))
    feels = float(main.get("feels_like", 0))
    humidity = int(main.get("humidity", 0))
    wind_ms = float(wind.get("speed", 0))
    cloud_pct = int(clouds.get("all", 0))

    return (
        f"Moti në {city}: {desc}. "
        f"Temp {temp:.1f}°C (ndihet {feels:.1f}°C). "
        f"Lageshtia {humidity}%. Re {cloud_pct}%. Era {wind_ms:.1f} m/s."
    )

@app.get("/ask")
def ask(q: str = Query(..., min_length=1, max_length=200)):
    text = q.strip().lower()

    # Ora
    if "ora" in text and len(text) <= 30:
        t = time.localtime()
        return ok(f"Ora tani është {t.tm_hour:02d}:{t.tm_min:02d}.")

    # Moti
    if text.startswith("moti"):
        # lejo: "moti ne tirane" / "moti tirane" / "moti në tiranë"
        city = "Tirane"
        parts = text.replace("ë", "e").split()
        if "ne" in parts:
            idx = parts.index("ne")
            if idx + 1 < len(parts):
                city = parts[idx + 1].capitalize()
        elif len(parts) >= 2:
            city = parts[-1].capitalize()

        try:
            return ok(weather_text(city))
        except Exception as e:
            return bad(str(e), 500)

    # Shembull “inteligjence” pa OpenAI (rule-based).
    # (Nqs do AI të vërtetë me model, bëhet, por mos posto çelësa këtu.)
    if "formula e dallorit" in text or "dallori" in text:
        return ok("Formula e dallorit: Δ = b² − 4ac.")

    return ok(f"Luna dëgjoi: {q}")

@app.post("/alarm/set")
def alarm_set(
    device_id: str = Query(..., min_length=1, max_length=64),
    at_epoch: int = Query(..., ge=0),
    city: str = Query("Tirane", min_length=1, max_length=64),
    message: str = Query("Zgjohu dhe shkelqe sot!", min_length=1, max_length=200),
):
    # ruaj alarm
    ALARMS[device_id] = {
        "at_epoch": int(at_epoch),
        "city": city,
        "message": message,
        "fired": False,
        "set_at": now_epoch(),
    }
    return {"ok": True, "device_id": device_id, "alarm": ALARMS[device_id]}

@app.get("/alarm/next")
def alarm_next(device_id: str = Query(..., min_length=1, max_length=64)):
    a = ALARMS.get(device_id)
    if not a:
        return {"ok": True, "has_alarm": False}

    # nqs ka rënë dhe s’e kemi “fired”, i kthejmë event
    now = now_epoch()
    at_epoch = int(a["at_epoch"])
    fired = bool(a.get("fired", False))

    if (now >= at_epoch) and (not fired):
        # shëno fired, dhe kthe payload me motin + mesazh
        a["fired"] = True
        city = a.get("city", "Tirane")
        msg = a.get("message", "Zgjohu dhe shkelqe sot!")

        weather = ""
        try:
            weather = weather_text(city)
        except Exception:
            weather = f"Moti në {city}: (s’u mor dot)."

        speak = f"{msg} {weather}"
        return {"ok": True, "has_alarm": True, "fire": True, "speak": speak, "at_epoch": at_epoch}

    # përndryshe thjesht status
    return {"ok": True, "has_alarm": True, "fire": False, "at_epoch": at_epoch}
