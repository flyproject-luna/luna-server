import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()

app = FastAPI()


class AskBody(BaseModel):
    text: str
    city: str | None = None


@app.get("/")
def root():
    return "ok"


@app.get("/health")
def health():
    return {"ok": True}


def get_weather(city: str):
    if not OPENWEATHER_API_KEY:
        return None
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric", "lang": "en"}
    r = requests.get(url, params=params, timeout=15)
    if r.status_code != 200:
        return None
    data = r.json()
    temp = data["main"]["temp"]
    hum = data["main"]["humidity"]
    wind = data["wind"]["speed"]
    desc = data["weather"][0]["description"]
    return f"Weather in {city}: {temp:.1f}°C, {desc}. Humidity {hum}%, wind {wind:.2f} m/s."


def ask_llm(prompt: str):
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY missing")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Luna, a helpful Albanian AI assistant. "
                    "Answer clearly and briefly. If user asks math, be exact. "
                    "If user asks a recipe, give steps + ingredients. "
                    "If user asks traffic, ask for city/route if missing."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.6,
        "max_tokens": 300,
    }

    r = requests.post(url, headers=headers, json=payload, timeout=30)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OpenRouter error: {r.text}")

    data = r.json()
    return data["choices"][0]["message"]["content"].strip()


@app.post("/ask")
def ask(body: AskBody):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    extra = ""
    if body.city:
        w = get_weather(body.city)
        if w:
            extra = f"\n\nContext:\n{w}"

    answer = ask_llm(text + extra)
    return {"ok": True, "answer": answer}


@app.get("/weather")
def weather(city: str = "Tirana"):
    w = get_weather(city)
    if not w:
        raise HTTPException(status_code=400, detail="Weather not available")
    return {"ok": True, "answer": w}
