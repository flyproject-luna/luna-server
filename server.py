from flask import Flask, request, jsonify
import os, requests
from datetime import datetime

app = Flask(__name__)

def now_text():
    return datetime.now().strftime("%H:%M")

def weather(city: str):
    api_key = os.getenv("OPENWEATHER_API_KEY", "")
    if not api_key:
        return None, "Mungon OPENWEATHER_API_KEY ne Render."
    url = "https://api.openweathermap.org/data/2.5/weather"
    r = requests.get(url, params={"q": city, "appid": api_key, "units": "metric", "lang": "sq"}, timeout=10)
    if r.status_code != 200:
        return None, f"Nuk e gjeta motin per '{city}'."
    data = r.json()
    desc = data["weather"][0]["description"]
    temp = round(data["main"]["temp"])
    feels = round(data["main"]["feels_like"])
    return f"Në {city}: {desc}, {temp}°C (ndjehet {feels}°C).", None

@app.get("/")
def home():
    return "LUNA server running ✅  Provo: /ask?q=ora ose /ask?q=moti ne londer"

@app.get("/ask")
def ask():
    q = (request.args.get("q", "") or "").strip().lower()
    if not q:
        return jsonify(ok=False, error="Mungon parametri q. Shembull: /ask?q=ora"), 400

    # ORA
    if "ora" in q:
        return jsonify(ok=True, answer=f"Ora është {now_text()}."), 200

    # MOTI
    if "moti" in q:
        # merr qytetin pas "ne"
        city = "Tiranë"
        if " ne " in q:
            city = q.split(" ne ", 1)[1].strip()
        if not city:
            city = "Tiranë"
        ans, err = weather(city)
        if err:
            return jsonify(ok=False, answer=err), 400
        return jsonify(ok=True, answer=ans), 200

    # FALLBACK
    return jsonify(ok=True, answer=f"Luna dëgjoi: {q}. (ende pa AI)"), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
