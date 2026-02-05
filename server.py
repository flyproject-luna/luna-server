from flask import Flask, request, jsonify
import os, random, re
from datetime import datetime
import requests

app = Flask(__name__)

BAD_WORDS = [
    "pidh", "kar", "mut", "qif", "kurv", "byth", "peder", "racist","bythqir","moterqir"
]

def sanitize(text: str) -> str:
    t = text
    for w in BAD_WORDS:
        t = re.sub(rf"\b{re.escape(w)}\w*\b", "***", t, flags=re.IGNORECASE)
    return t

def now_time_str():
    # pa timezone lib ekstra - mjafton për tani
    return datetime.now().strftime("%H:%M")

def extract_city(q: str):
    # "moti ne london" / "moti në london" / "weather in london"
    q2 = q.lower().replace("në", "ne").strip()
    m = re.search(r"(?:moti|weather)\s+(?:ne|in)\s+(.+)$", q2)
    if m:
        return m.group(1).strip()
    # fallback: fjala e fundit
    parts = q2.split()
    return parts[-1].strip() if parts else None

def get_weather(city: str):
    key = os.getenv("OPENWEATHER_KEY")
    if not key:
        return None, "OPENWEATHER_KEY mungon ne Render Environment"

    # Current weather endpoint (q=city)
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": key,
        "units": "metric",
        "lang": "sq"
    }
    r = requests.get(url, params=params, timeout=10)
    if r.status_code != 200:
        return None, f"Weather error {r.status_code}: {r.text[:120]}"
    data = r.json()

    name = data.get("name", city)
    main = data.get("main", {})
    wind = data.get("wind", {})
    weather_list = data.get("weather", [])
    desc = weather_list[0].get("description", "pa pershkrim") if weather_list else "pa pershkrim"

    temp = main.get("temp")
    feels = main.get("feels_like")
    hum = main.get("humidity")
    w = wind.get("speed")

    text = f"Moti ne {name}: {desc}. Temp {temp}°C (ndihet {feels}°C). Lageshtia {hum}%. Era {w} m/s."
    return text, None

JOKES = [
    "Pse kompjuteri s’fjeti? Se kishte shume tabs hapur.",
    "Pse WiFi u merzit? Se s’e dinte password-in.",
    "Pse serveri u nervozua? Se i vinin request-e pa endpoint."
]

@app.get("/")
def home():
    return "LUNA server running ✅ Shko te: /ask?q=pershendetje"

@app.get("/ask")
def ask():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify(ok=False, error="Mungon parametri q. Shembull: /ask?q=ora"), 400

    q_clean = sanitize(q)
    q_low = q_clean.lower()

    # ORA
    if q_low in ["ora", "sa eshte ora", "sa eshte ora tani"]:
        return jsonify(ok=True, answer=f"Ora tani eshte {now_time_str()}."), 200

    # BARCALETA
    if "barcalet" in q_low or "barcaleta" in q_low:
        return jsonify(ok=True, answer=random.choice(JOKES)), 200

    # MOTI
    if q_low.startswith("moti") or q_low.startswith("weather"):
        city = extract_city(q_clean)
        if not city:
            return jsonify(ok=False, error="Shkruaj p.sh: moti ne london"), 400
        ans, err = get_weather(city)
        if err:
            return jsonify(ok=False, error=err), 500
        return jsonify(ok=True, answer=ans), 200

    # DEFAULT (per tani pa AI)
    return jsonify(ok=True, answer=f"Luna degjoi: {q_clean}"), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
