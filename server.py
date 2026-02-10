import os
import re
import ast
import math
import requests
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from ddgs import DDGS  # për web search falas

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "").strip()  # Shto key tënd falas nga developer.tomtom.com

MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()

app = FastAPI()

class AskBody(BaseModel):
    text: str
    city: str | None = None
    name: str | None = None
    family: str | None = None
    device_id: str | None = None

@app.get("/")
def root():
    return "ok"

@app.get("/health")
def health():
    return {"ok": True, "time_utc": datetime.now(timezone.utc).isoformat()}

def get_weather(city: str) -> str | None:
    if not OPENWEATHER_API_KEY:
        return None
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric", "lang": "sq"}
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        temp = data["main"]["temp"]
        hum = data["main"]["humidity"]
        wind = data["wind"]["speed"]
        desc = data["weather"][0]["description"]
        return f"Moti në {city}: {temp:.1f}°C, {desc}. Lagështia {hum}%, era {wind:.2f} m/s."
    except Exception:
        return None

def get_traffic(city: str) -> str | None:
    if not TOMTOM_API_KEY:
        return None
    try:
        url = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
        params = {"key": TOMTOM_API_KEY, "point": "41.3275,19.8187"}  # Koordinata për Tiranën – ndrysho për city
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        speed = data["flowSegmentData"]["currentSpeed"]
        free_speed = data["flowSegmentData"]["freeFlowSpeed"]
        return f"Trafiku në {city}: Shpejtësia aktuale {speed} km/h (normale {free_speed} km/h)."
    except Exception:
        return None

# ---- Safe math ----
# (mbaj të njëjtën si më parë)

def safe_eval_math(expr: str) -> str | None:
    # (kod i mëparshëm pa ndryshim)

def is_factual_query(text: str) -> bool:
    keywords = ["çfarë", "si", "kush", "kur", "pse", "sa", "ku", "formula", "trafik", "moti"]
    return any(word in text.lower() for word in keywords)

def web_search(query: str) -> str:
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=2)]
        if not results:
            return ""
        sources = "\nVerifikim në 2 burime:\n"
        for res in results:
            sources += f"{res['body']}\n"
        return sources  # Mos thuaj burimet në përgjigje
    except Exception as e:
        print(f"Gabim web: {e}")
        return ""

def ask_llm(prompt: str) -> str:
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY missing")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    system = (
        "Ti je Luna, asistent logjik dhe kujdesshëm shqip.\n"
        "Rregulla:\n"
        "- Përgjigju në shqip, me fjali të shkurtra, precize dhe korrekte.\n"
        "- Mos përmend burime ose links – jep vetëm informacionin e pastër.\n"
        "- Double-check 3 herë: Mendo hap pas hapi, verifiko logjikën 3 herë, kontrollo në 2 burime (përdor kontekstin).\n"
        "- Ji korrekt: Mos përdor fjalë banale, fol qartë dhe logjikisht.\n"
        "- Për YouTube: Nëse 'play [song]', kthe 'Link: https://youtube.com/search?q=[song]'.\n"
        - "Për kohën: Thuaj 'Ora është [HH:MM]'.\n"
        - "Për trafik: Përdor kontekstin për të dhëna të sakta.\n"
        - "Për alarm: Konfirmo vendosjen."
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,  # Më i ulët për precizitet
        "max_tokens": 200,  # Fjali të shkurtra
    }

    r = requests.post(url, headers=headers, json=payload, timeout=35)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Groq error: {r.text}")

    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

@app.post("/ask")
def ask(body: AskBody):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    math_ans = safe_eval_math(text)
    if math_ans is not None:
        return {"ok": True, "answer": math_ans}

    name = (body.name or "").strip()
    city = (body.city or "").strip()
    family = (body.family or "").strip()

    ctx = []
    if name:
        ctx.append(f"Emri: {name}")
    if city:
        ctx.append(f"Qyteti: {city}")
    if family:
        ctx.append(f"Familja: {family}")

    w = get_weather(city) if city else None
    if w:
        ctx.append(w)

    t = get_traffic(city) if city else None
    if t:
        ctx.append(t)

    web = ""
    if is_factual_query(text):
        web = web_search(text)

    context_block = "\nKontekst:\n- " + "\n- ".join(ctx) + web if (ctx or web) else ""

    answer = ask_llm(text + context_block)
    return {"ok": True, "answer": answer}

# (mbaj /weather si më parë)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
