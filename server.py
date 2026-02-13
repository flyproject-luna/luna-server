import os
import requests
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from ddgs import DDGS

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "").strip()
MODEL = os.getenv("GROQ_MODEL", "gemma2-9b-it").strip()

app = FastAPI(title="Luna AI Full 2026")

class AskBody(BaseModel):
    text: str | None = None
    q: str | None = None
    city: str | None = None
    name: str | None = None
    family: str | None = None
    device_id: str | None = None

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/health")
def health():
    return {"ok": True, "time": datetime.now().strftime("%H:%M:%S")}

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

def ask_groq(prompt):
    if not GROQ_API_KEY:
        return "Mungon GROQ_API_KEY"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Ti je Luna, asistente inteligjente shqip. Jep përgjigje të shkurtra, të sakta, pa shpikje."
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 150
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

# ---------------- ASK ROUTE ----------------

@app.post("/ask")
def ask(body: AskBody):

    text = (body.text or body.q or "").strip()

    if not text:
        raise HTTPException(400, "Tekst bosh")

    city = body.city or "Tirana"

    context = []
    context.append(f"Ora: {datetime.now().strftime('%H:%M')}")
    w = get_weather(city)
    if w:
        context.append(w)

    web = ""
    if len(text.split()) > 6:
        web = web_search(text)

    full_prompt = text + "\n\nKontekst:\n" + "\n".join(context) + "\n" + web

    answer = ask_groq(full_prompt)

    return {
        "ok": True,
        "answer": answer
    }

# ---------------- RUN ----------------

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
