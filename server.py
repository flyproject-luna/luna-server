from fastapi import FastAPI, Query
import requests, os, datetime

app = FastAPI()

OPENWEATHER_KEY = os.getenv("OPENWEATHER_API_KEY")

@app.get("/")
def root():
    return {"status": "Luna server online", "ok": True}

@app.get("/ask")
def ask(q: str = Query(...)):

    q = q.lower().strip()

    # ORA
    if "ora" in q:
        now = datetime.datetime.now().strftime("%H:%M")
        return {"answer": f"Ora tani eshte {now}.", "ok": True}

    # BARCALETA
    if "barcalet" in q:
        return {
            "answer": "Pse programuesit ngatërrojnë Halloween me Krishtlindje? Sepse OCT 31 == DEC 25 😄",
            "ok": True
        }

    # MOTI
    if "moti" in q:
        if not OPENWEATHER_KEY:
            return {"error": "OPENWEATHER_KEY mungon", "ok": False}

        qyteti = q.replace("moti", "").replace("ne", "").strip()
        if qyteti == "":
            qyteti = "tirane"

        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?q={qyteti}&appid={OPENWEATHER_KEY}&units=metric&lang=sq"
        )

        r = requests.get(url)
        if r.status_code != 200:
            return {"error": f"City not found ({qyteti})", "ok": False}

        d = r.json()
        temp = d["main"]["temp"]
        feels = d["main"]["feels_like"]
        hum = d["main"]["humidity"]
        wind = d["wind"]["speed"]
        desc = d["weather"][0]["description"]

        return {
            "answer": (
                f"Moti ne {qyteti.title()}: {desc}. "
                f"Temperatura {temp}°C (ndjehet {feels}°C). "
                f"Lageshtia {hum}%. Era {wind} m/s."
            ),
            "ok": True
        }

    # FALLBACK (AI basic)
    return {
        "answer": f"Luna degjoi: {q}",
        "ok": True
    }
