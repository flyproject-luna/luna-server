import os
import requests
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from ddgs import DDGS

# ---------------- CONFIG ----------------

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
MODEL = os.getenv("GROQ_MODEL", "llama3-70b-8192").strip()

app = FastAPI(title="Luna AI 2026")

# ---------------- MODEL ----------------

class AskBody(BaseModel):
    text: Optional[str] = None
    q: Optional[str] = None
    city: Optional[str] = "Tirana"
    name: Optional[str] = None
    family: Optional[str] = None
    device_id: Optional[str] = None

# ---------------- ROUTES ----------------

@app.get("/")
def root():
    return {"status": "ok", "ai": "Luna 2026"}

@app.get("/health")
def health():
    return {"ok": True, "time": datetime.now().strftime("%H:%M:%S"), "model": MODEL}

# ---------------- WEATHER ----------------

def get_weather(city="Tirana"):
    if not OPENWEATHER_API_KEY:
        return ""

    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "q": city,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric",
                "lang": "sq"
            },
            timeout=6
        )
        r.raise_for_status()
        d = r.json()
        return f"Moti në {city}: {d['main']['temp']:.1f}°C, {d['weather'][0]['description']}."
    except:
        return ""

# ---------------- WEB SEARCH ----------------

def web_search(query):
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=2)]
        return "\n".join(r["body"] for r in results)
    except:
        return ""

# ---------------- GROQ ----------------

def ask_ai(prompt):

    if not GROQ_API_KEY:
        return "GROQ_API_KEY mungon"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Ti je Luna, asistente inteligjente shqip. Jep përgjigje të sakta, të shkurtra, pa shpikje."
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 180
    }

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=15
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except:
        return "Gabim lidhje me AI"

# ---------------- ASK ----------------

@app.post("/ask")
def ask(body: AskBody):

    text = (body.text or body.q or "").strip()

    if not text:
        raise HTTPException(400, "Tekst bosh")

    city = body.city or "Tirana"

    context_parts = []

    context_parts.append(f"Ora: {datetime.now().strftime('%H:%M')}")

    weather = get_weather(city)
    if weather:
        context_parts.append(weather)

    if len(text.split()) > 6:
        web = web_search(text)
        if web:
            context_parts.append(web)

    full_prompt = text + "\n\nKontekst:\n" + "\n".join(context_parts)

    answer = ask_ai(full_prompt)

    return {
        "ok": True,
        "answer": answer
    }

# ---------------- RUN ----------------

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
