import os
import re
import ast
import math
import requests
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from ddgs import DDGS

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "").strip()

MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()

app = FastAPI(title="Luna - Asistent Inteligjent")

class AskBody(BaseModel):
    text: str
    city: str | None = None
    name: str | None = None
    family: str | None = None
    device_id: str | None = None

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/health")
def health():
    return {"ok": True}

def get_weather(city: str) -> str | None:
    if not OPENWEATHER_API_KEY or not city:
        return None
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric", "lang": "sq"}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        temp = data["main"]["temp"]
        desc = data["weather"][0]["description"]
        return f"Moti në {city}: {temp:.1f}°C, {desc}."
    except:
        return None

def get_traffic(city: str) -> str | None:
    if not TOMTOM_API_KEY or not city:
        return None
    try:
        # Koordinata shembull për Tiranën – mund të shtosh geocode për qytete të tjera
        url = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
        params = {"key": TOMTOM_API_KEY, "point": "41.3275,19.8187"}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        speed = data["flowSegmentData"]["currentSpeed"]
        free = data["flowSegmentData"]["freeFlowSpeed"]
        return f"Trafiku në {city}: {speed} km/h (normale {free} km/h)."
    except:
        return None

def safe_eval_math(expr: str) -> str | None:
    expr = expr.strip()
    if not re.fullmatch(r"[0-9\.\+\-\*\/\(\)\s]+", expr):
        return None
    try:
        return str(eval(expr, {"__builtins__": {}}, {}))
    except:
        return None

def web_search(query: str) -> str:
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=2)]
        if not results:
            return ""
        context = "\n".join(r["body"] for r in results)
        return context
    except:
        return ""

def is_factual_query(text: str) -> bool:
    keywords = ["çfarë", "kush", "ku", "kur", "pse", "sa", "si", "formula", "trafik", "moti", "histori"]
    return any(word in text.lower() for word in keywords)

def ask_groq(prompt: str) -> str:
    if not GROQ_API_KEY:
        raise HTTPException(500, "GROQ_API_KEY mungon")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    system = (
        "Ti je Luna, asistent inteligjent shqip si Alexa.\n"
        "Përgjigju:\n"
        "- Në shqip të pastër dhe korrekt\n"
        "- Fjali të shkurtra dhe të drejtpërdrejta\n"
        "- Pa fjalë banale, pa 'super', 'fantastik', 'wow'\n"
        "- Pa përmendur burime ose links\n"
        "- Verifiko fakte me 2 burime para se të përgjigjesh\n"
        "- Nëse nuk je e sigurt, thuaj 'Nuk jam e sigurt'\n"
        "- Për 'play [këngë]': thuaj 'Link: https://youtube.com/results?search_query=[këngë]'\n"
        "- Për orë: 'Ora është HH:MM'\n"
        "- Për trafik/moti: përdor kontekstin e dhënë\n"
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 180,
    }

    r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()

@app.post("/ask")
def ask(body: AskBody):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "Tekst bosh")

    math_ans = safe_eval_math(text)
    if math_ans is not None:
        return {"ok": True, "answer": math_ans}

    ctx = []
    if body.name:
        ctx.append(f"Emri: {body.name}")
    if body.city:
        ctx.append(f"Qyteti: {body.city}")
        w = get_weather(body.city)
        if w: ctx.append(w)
        t = get_traffic(body.city)
        if t: ctx.append(t)
    if body.family:
        ctx.append(f"Familja: {body.family}")

    web = ""
    if is_factual_query(text):
        web = web_search(text)

    context = "\n".join(ctx) + "\n" + web if (ctx or web) else ""

    full_prompt = text + "\nKontekst:\n" + context if context else text

    answer = ask_groq(full_prompt)
    return {"ok": True, "answer": answer}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
