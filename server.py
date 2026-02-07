import os
import time
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="luna-server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

START_TIME = time.time()

def env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    return v.strip()

@app.get("/", response_class=PlainTextResponse)
def root():
    return "ok"

@app.get("/health")
def health():
    return {
        "status": "ok",
        "uptime_s": int(time.time() - START_TIME),
    }

@app.get("/weather")
def weather(city: str = "Tirana"):
    key = env("OPENWEATHER_API_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="OPENWEATHER_API_KEY missing")

    # OpenWeather current weather endpoint
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": key, "units": "metric", "lang": "en"}

    try:
        r = requests.get(url, params=params, timeout=12)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"weather_request_failed: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"weather_bad_status: {r.status_code} {r.text[:200]}")

    data = r.json()
    temp = data["main"]["temp"]
    desc = data["weather"][0]["description"]
    hum = data["main"]["humidity"]
    wind = data.get("wind", {}).get("speed", 0)

    return {
        "city": city,
        "temp_c": temp,
        "description": desc,
        "humidity": hum,
        "wind_m_s": wind,
    }

@app.exception_handler(Exception)
def any_exception_handler(request, exc: Exception):
    # që të mos rrëzohet procesi pa output
    return PlainTextResponse(f"server_error: {type(exc).__name__}: {exc}", status_code=500)
