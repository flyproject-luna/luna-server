import os
import json
import time
from datetime import datetime, timezone, timedelta

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ====== Settings ======
TZ_OFFSET_HOURS = 1  # Shqipëri zakonisht +1 (dimër). Ndrysho në +2 verë nëse do.
DATA_FILE = "alarm.json"

DEFAULT_CITY = "Tirane"

def now_local():
    return datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)

def load_alarm():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return None
    return None

def save_alarm(alarm: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(alarm, f, ensure_ascii=False)

def clear_alarm():
    if os.path.exists(DATA_FILE):
        try:
            os.remove(DATA_FILE)
        except:
            pass

def weather_city(city: str):
    key = os.getenv("OPENWEATHER_API_KEY")
    if not key:
        return None, "OPENWEATHER_API_KEY mungon ne Render Environment"
    # current weather
    url = "https://api.openweathermap.org/data/2.5/weather"
    r = requests.get(url, params={"q": city, "appid": key, "units": "metric", "lang": "sq"}, timeout=12)
    if r.status_code != 200:
        return None, f"Weather error {r.status_code}: {r.text}"
    return r.json(), None

def format_weather(city: str):
    data, err = weather_city(city)
    if err:
        return None, err
    main = data.get("main", {})
    wind = data.get("wind", {})
    clouds = data.get("clouds", {})
    desc = ""
    wlist = data.get("weather", [])
    if wlist and isinstance(wlist, list):
        desc = wlist[0].get("description", "")
    t = main.get("temp")
    feels = main.get("feels_like")
    hum = main.get("humidity")
    ws = wind.get("speed")
    cl = clouds.get("all")
    msg = f"Moti ne {city}: {desc}. Temp {t}°C (ndihet {feels}°C). Lageshtia {hum}%. Retë {cl}%. Era {ws} m/s."
    return msg, None

def parse_city_from_query(q: str):
    q = q.strip().lower()
    # "moti ne tirane" / "moti ne london"
    if "moti" in q and "ne " in q:
        city = q.split("ne ", 1)[1].strip()
        if city:
            # titullizo pak
            return city[:1].upper() + city[1:]
    return None

# ====== Routes ======

@app.get("/")
def home():
    return "Luna server OK"

@app.get("/health")
def health():
    return jsonify(ok=True, ts=int(time.time()))

@app.get("/time")
def get_time():
    t = now_local()
    return jsonify(ok=True, time=t.strftime("%H:%M"), iso=t.isoformat())

@app.get("/ask")
def ask():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify(ok=False, error="Missing q"), 400

    qlow = q.lower().strip()

    # ora
    if "ora" == qlow or "sa eshte ora" in qlow:
        t = now_local().strftime("%H:%M")
        return jsonify(ok=True, answer=f"Ora tani eshte {t}.")

    # moti
    if qlow.startswith("moti"):
        city = parse_city_from_query(q) or DEFAULT_CITY
        msg, err = format_weather(city)
        if err:
            return jsonify(ok=False, error=err), 500
        return jsonify(ok=True, answer=msg)

    # fallback (pa “AI” te jashtme)
    return jsonify(ok=True, answer=f"Luna degjoi: {q}")

# Browseri bën GET, prandaj mos i kthe 404
@app.get("/alarm/set")
def alarm_set_get():
    return jsonify(ok=False, error="Use POST /alarm/set with JSON body"), 405

@app.post("/alarm/set")
def alarm_set():
    data = request.get_json(silent=True) or {}
    try:
        hour = int(data.get("hour"))
        minute = int(data.get("minute"))
    except:
        return jsonify(ok=False, error="hour/minute required (ints)"), 400

    city = (data.get("city") or DEFAULT_CITY).strip()
    message = (data.get("message") or "Zgjohu dhe shkelqe sot").strip()

    alarm = {
        "enabled": True,
        "hour": hour,
        "minute": minute,
        "city": city,
        "message": message,
        "created_ts": int(time.time()),
        "last_fired_ts": 0
    }
    save_alarm(alarm)
    return jsonify(ok=True, alarm=alarm)

@app.get("/alarm/get")
def alarm_get():
    alarm = load_alarm()
    if not alarm:
        return jsonify(ok=True, enabled=False)

    # për siguri
    alarm.setdefault("enabled", True)
    alarm.setdefault("last_fired_ts", 0)

    return jsonify(ok=True, **alarm)

@app.post("/alarm/clear")
def alarm_clear():
    clear_alarm()
    return jsonify(ok=True)

@app.get("/alarm/next")
def alarm_next():
    alarm = load_alarm()
    if not alarm or not alarm.get("enabled"):
        return jsonify(ok=True, enabled=False)

    # thjesht kthen orën e alarmit
    return jsonify(ok=True, enabled=True, hour=alarm.get("hour"), minute=alarm.get("minute"))

if __name__ == "__main__":
    # Render përdor PORT env
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
