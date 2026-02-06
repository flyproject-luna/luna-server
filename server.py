import os
import re
import time
from datetime import datetime, timezone

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ----------------------------
# CONFIG (ENV)
# ----------------------------
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
TZ_NAME = os.getenv("TZ_NAME", "Europe/Tirane")

# In-memory alarm store (mjafton për tani; për prodhim duhej DB/Redis)
ALARM = {
    "enabled": False,
    "epoch": 0,
    "time": "",
    "message": ""
}

# ----------------------------
# Helpers
# ----------------------------
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def normalize_city(raw: str) -> str:
    s = raw.strip().lower()
    s = s.replace("ë", "e").replace("ç", "c")
    # mapping i thjeshtë për pyetjet e tua
    if s in ["tirane", "tirana"]:
        return "Tirana,AL"
    if s in ["londer", "london"]:
        return "London,GB"
    # nëse shkruan qytetin direkt, e lëmë siç është
    return raw.strip()

def albanian_weather_text(city_display: str, data: dict) -> str:
    main = data.get("main", {})
    wind = data.get("wind", {})
    weather = (data.get("weather") or [{}])[0]

    temp = main.get("temp")
    feels = main.get("feels_like")
    hum = main.get("humidity")
    wind_ms = wind.get("speed")
    desc = (weather.get("description") or "").lower()

    # përkthim shumë i thjeshtë
    desc_map = {
        "clear sky": "qiell i kthjellët",
        "few clouds": "pak re",
        "scattered clouds": "re të shpërndara",
        "broken clouds": "shumë re",
        "overcast clouds": "i mbuluar me re",
        "light rain": "shi i lehtë",
        "moderate rain": "shi mesatar",
        "heavy intensity rain": "shi i fortë",
        "snow": "borë",
        "mist": "mjegull",
        "fog": "mjegull e dendur",
        "haze": "muzg",
        "thunderstorm": "stuhi me rrufe",
    }
    desc_sq = desc_map.get(desc, desc if desc else "moti")

    parts = []
    parts.append(f"Moti në {city_display}: {desc_sq}.")
    if temp is not None:
        parts.append(f"Temp {temp:.1f}°C")
    if feels is not None:
        parts.append(f"(ndihet {feels:.1f}°C)")
    if hum is not None:
        parts.append(f"Lagështia {hum}%")
    if wind_ms is not None:
        parts.append(f"Era {wind_ms:.1f} m/s")
    return " ".join(parts) + "."

def get_weather(city: str) -> dict:
    if not OPENWEATHER_API_KEY:
        raise RuntimeError("OPENWEATHER_API_KEY mungon")

    # OpenWeather Current Weather
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "en",
    }
    r = requests.get(url, params=params, timeout=12)
    if r.status_code != 200:
        # kthe tekst të qartë për debug
        return {"ok": False, "status": r.status_code, "body": r.text}
    return {"ok": True, "data": r.json()}

def parse_alarm_time_to_epoch(hhmm: str) -> int:
    # Interpretim: alarmi është sot në atë orë, në timezone lokale.
    # Për thjeshtësi (pa pytz), llogarisim me epoch UTC duke supozuar se serveri ka TZ të saktë.
    # Në Fly/Railway mund ta vendosësh TZ=Europe/Tirane.
    now = datetime.now()
    m = re.match(r"^(\d{1,2}):(\d{2})$", hhmm.strip())
    if not m:
        raise ValueError("Formati i orës duhet HH:MM")
    hh = int(m.group(1))
    mm = int(m.group(2))
    candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if candidate.timestamp() < time.time():
        candidate = candidate.replace(day=now.day)  # keep
        candidate = candidate.fromtimestamp(candidate.timestamp() + 24 * 3600)
    return int(candidate.timestamp())

# ----------------------------
# Routes
# ----------------------------
@app.get("/")
def root():
    return jsonify({
        "service": "luna-server",
        "ok": True,
        "time_utc": now_iso(),
        "endpoints": ["/health", "/ask?q=", "/alarm/set", "/alarm/next", "/alarm/clear"]
    })

@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "luna-server", "time_utc": now_iso()})

@app.get("/ask")
def ask():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"ok": False, "error": "Missing q"}), 400

    q_l = q.lower().strip()
    q_l = q_l.replace("ë", "e").replace("ç", "c")

    # ORA
    if q_l in ["ora", "sa eshte ora", "sa eshte ora tani"]:
        local = datetime.now().strftime("%H:%M")
        return jsonify({"ok": True, "answer": f"Ora tani është {local}."})

    # MOTI
    if q_l.startswith("moti"):
        # pranon: "moti ne tirane" / "moti ne london"
        m = re.search(r"moti\s+ne\s+(.+)$", q_l)
        city_raw = m.group(1).strip() if m else "Tirana,AL"
        city = normalize_city(city_raw)
        w = get_weather(city)
        if not w["ok"]:
            return jsonify({"ok": False, "error": f"Weather error {w['status']}: {w['body']}"}), 500
        data = w["data"]
        city_display = data.get("name") or city_raw
        text = albanian_weather_text(city_display, data)
        return jsonify({"ok": True, "answer": text})

    # Default
    return jsonify({"ok": True, "answer": f"Luna dëgjoi: {q}."})

@app.post("/alarm/set")
def alarm_set():
    body = request.get_json(silent=True) or {}
    hhmm = str(body.get("time", "")).strip()
    message = str(body.get("message", "")).strip() or "Zgjohu dhe shkëlqe sot."

    if not hhmm:
        return jsonify({"ok": False, "error": "Missing 'time' (HH:MM)"}), 400

    try:
        epoch = parse_alarm_time_to_epoch(hhmm)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    ALARM["enabled"] = True
    ALARM["epoch"] = epoch
    ALARM["time"] = hhmm
    ALARM["message"] = message

    return jsonify({"ok": True, "alarm": ALARM})

@app.get("/alarm/next")
def alarm_next():
    if not ALARM["enabled"]:
        return jsonify({"ok": True, "enabled": False})

    now = int(time.time())
    due = now >= int(ALARM["epoch"])
    return jsonify({
        "ok": True,
        "enabled": True,
        "epoch": int(ALARM["epoch"]),
        "due": bool(due),
        "time": ALARM["time"],
        "message": ALARM["message"]
    })

@app.post("/alarm/clear")
def alarm_clear():
    ALARM["enabled"] = False
    ALARM["epoch"] = 0
    ALARM["time"] = ""
    ALARM["message"] = ""
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
