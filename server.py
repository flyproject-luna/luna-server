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

MODEL = os.getenv("GROQ_MODEL", "gemma2-9b-it").strip()  # Model i saktë dhe konciz

app = FastAPI(title="Luna Server")

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

def get_weather(city: str = "Tirana") -> str | None:
    if not OPENWEATHER_API_KEY:
        return None
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric", "lang": "sq"}
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        temp = data["main"]["temp"]
        desc = data["weather"][0]["description"]
        return f"Moti në {city}: {temp:.1f}°C, {desc}."
    except:
        return None

def get_traffic(city: str = "Tirana") -> str | None:
    if not TOMTOM_API_KEY:
        return None
    try:
        # Koordinata Tirana (41.3275, 19.8187) – mund të shtosh geocode më vonë
        url = "https://api.tomtom.com/traffic/services/4/incidents/search.json"
        params = {
            "key": TOMTOM_API_KEY,
            "bbox": "19.7,41.2,19.9,41.4",  # Bounding box rreth Tiranës
            "fields": "incidents{type,geometry{type,coordinates},properties{iconCategory,description}}",
            "language": "sq",
            "limit": 3
        }
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        if not data.get("incidents"):
            return f"Nuk ka incidente të raportuara në {city} tani."
        incidents = data["incidents"]
        desc = ", ".join(i["properties"]["description"] for i in incidents[:2])
        return f"Trafiku në {city}: {desc}"
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
        return "\n".join(r["body"] for r in results)
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
        "Ti je Luna, asistent inteligjent shqip.\n"
        "Rregulla:\n"
        "- Përgjigju vetëm me fakte të sakta.\n"
        "- Fjali të shkurtra, të drejtpërdrejta.\n"
        "- Pa fjalë të panevojshme.\n"
        "- Pa përmendur burime ose links.\n"
        "- Nëse nuk ke të dhëna të sakta, thuaj 'Nuk e di saktë'.\n"
        "- Për orën: përdor kohën aktuale.\n"
        "- Për motin/trafikun: përdor vetëm të dhënat e dhëna.\n"
        "- Për 'play [këngë]': thuaj 'Link: https://youtube.com/results?search_query=[këngë]'.\n"
        "- Mos shpik asgjë.\n"
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,  # shumë i ulët për saktësi maksimale
        "max_tokens": 150,
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

    city = body.city or "Tirana"  # Default Tirana

    ctx = []
    if body.name:
        ctx.append(f"Emri: {body.name}")
    if body.family:
        ctx.append(f"Familja: {body.family}")

    w = get_weather(city)
    if w:
        ctx.append(w)

    t = get_traffic(city)
    if t:
        ctx.append(t)

    current_time = datetime.now().strftime("%H:%M")
    ctx.append(f"Ora aktuale: {current_time}")

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
