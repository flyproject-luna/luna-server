import os
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

@app.get("/")
def root():
    return {"ok": True, "message": "Luna server online"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/ask")
async def ask(req: Request):
    data = await req.json()
    question = data.get("question", "").lower()
    city = data.get("city", "Tirana")

    if "weather" in question or "moti" in question:
        if not OPENWEATHER_API_KEY:
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Missing OpenWeather API key"}
            )

        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
        )
        r = requests.get(url)
        if r.status_code != 200:
            return {"ok": False, "error": "Weather API failed"}

        w = r.json()
        temp = w["main"]["temp"]
        desc = w["weather"][0]["description"]

        return {
            "ok": True,
            "answer": f"Në {city} temperatura është {temp}°C me {desc}"
        }

    return {
        "ok": True,
        "answer": "Jam Luna. Mund të më pyesësh për motin ose alarmet."
    }
