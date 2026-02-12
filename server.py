import os
import re
import requests
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from ddgs import DDGS

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "").strip()

MODEL = os.getenv("GROQ_MODEL", "gemma2-9b-it").strip()

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
        url = "https://api.tomtom.com/traffic/services/4/incidents/search.json"
        params = {
            "key": TOMTOM_API_KEY,
            "bbox": "19.7,41.2,19.9,41.4",
            "fields": "incidents{properties{description}}",
            "language": "sq",
            "limit": 2
        }
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        if not data.get("incidents"):
            return f"Nuk ka incidente në {city} tani."
        desc = ", ".join(i["properties"]["description"] for i in data["incidents"])
        return f"Trafiku në {city}: {desc}"
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
    keywords = ["çfarë", "kush", "ku", "kur", "pse", "sa", "si", "formula", "trafik", "moti"]
    return any(word in text.lower() for word in keywords)

def get_edge_tts_url(text: str) -> str:
    # Microsoft Edge TTS (Neural) – zë femëror shqip natyral
    # sq-AL-NoraNeural ose sq-AL-AnilaNeural – Nora është më femërore dhe natyrale
    voice = "sq-AL-NoraNeural"
    url = f"https://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1?trustedclienttoken=6A5AA1D4EAFF4E9FB37E23D68491D6F4"
    payload = {
        "text": text,
        "ssml": f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="sq-AL"><voice name="{voice}">{text}</voice></speak>',
        "rate": 1.0,
        "pitch": 0,
        "volume": 100
    }
    headers = {
        "Content-Type": "application/ssml+xml",
        "User-Agent": "Mozilla/5.0",
        "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3"
    }
    r = requests.post(url, json=payload, headers=headers, stream=True)
    if r.status_code == 200:
        # Kthe stream URL ose base64 – për ESP32 më mirë stream
        return "stream_url"  # Në praktikë ruaj në S3 ose kthe direkt stream
    return ""

def ask_groq(prompt: str) -> str:
    if not GROQ_API_KEY:
        raise HTTPException(500, "GROQ_API_KEY mungon")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    system = (
        "Ti je Luna, asistent inteligjent shqip.\n"
        "Përgjigju:\n"
        "- Vetëm me fakte të sakta.\n"
        "- Fjali të shkurtra dhe të drejtpërdrejta.\n"
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
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "temperature": 0.2,
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

    city = body.city or "Tirana"

    ctx = []
    if body.name:
        ctx.append(f"Emri: {body.name}")
    if body.family:
        ctx.append(f"Familja: {body.family}")

    w = get_weather(city)
    if w: ctx.append(w)

    t = get_traffic(city)
    if t: ctx.append(t)

    current_time = datetime.now().strftime("%H:%M")
    ctx.append(f"Ora aktuale: {current_time}")

    web = ""
    if is_factual_query(text):
        web = web_search(text)

    context = "\n".join(ctx) + "\n" + web if (ctx or web) else ""

    full_prompt = text + "\nKontekst:\n" + context if context else text

    answer = ask_groq(full_prompt)

    audio_url = get_edge_tts_url(answer)  # Zë femëror natyral shqip nga Microsoft Edge TTS

    return {"ok": True, "answer": answer, "audio_url": audio_url}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
