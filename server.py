from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

@app.get("/")
def home():
    return "LUNA server running"

@app.get("/ask")
def ask():
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify(ok=False, error="mungon parametri q"), 400

    # ORA
    if "ora" in q:
        return jsonify(ok=True, answer="Luna degjoi: ora")

    # MOTI
    if "moti" in q:
        city = "london"
        if "londer" in q:
            city = "london"
        elif "tirane" in q:
            city = "tirana"

        # API i thjeshtë (Open-Meteo, pa key)
        geo = {
            "london": (51.5072, -0.1276),
            "tirana": (41.3275, 19.8187),
        }
        lat, lon = geo.get(city, geo["london"])
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        r = requests.get(url, timeout=5)
        data = r.json()
        temp = data["current_weather"]["temperature"]

        return jsonify(ok=True, answer=f"Moti ne {city}: {temp}°C")

    return jsonify(ok=False, error="komande e panjohur"), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
