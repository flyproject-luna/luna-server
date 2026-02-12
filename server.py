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

app = FastAPI(title="Luna Server - Version i plote dhe i zgjeruar")

class AskBody(BaseModel):
    text: str
    city: str | None = None
    name: str | None = None
    family: str | None = None
    device_id: str | None = None

@app.get("/")
def root():
    return {"status": "ok", "version": "Luna Full 2026"}

@app.get("/health")
def health():
    return {"ok": True, "time": datetime.now().strftime("%H:%M:%S"), "model": MODEL}

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
        humidity = data["main"]["humidity"]
        wind = data["wind"]["speed"]
        return f"Moti në {city}: {temp:.1f}°C, {desc}. Lagështia {humidity}%, era {wind} m/s."
    except Exception as e:
        print(f"Weather error for {city}: {e}")
        return None

def get_traffic(city: str = "Tirana") -> str | None:
    if not TOMTOM_API_KEY:
        return None
    try:
        url = "https://api.tomtom.com/traffic/services/4/incidents/search.json"
        params = {
            "key": TOMTOM_API_KEY,
            "bbox": "19.7,41.2,19.9,41.4",
            "fields": "incidents{properties{description,iconCategory}}",
            "language": "sq",
            "limit": 3
        }
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        if not data.get("incidents"):
            return f"Nuk ka incidente të raportuara në {city} tani."
        incidents = []
        for inc in data["incidents"][:2]:
            desc = inc["properties"].get("description", "incident")
            icon = inc["properties"].get("iconCategory", "unknown")
            incidents.append(f"{desc} ({icon})")
        return f"Trafiku në {city}: {', '.join(incidents)}"
    except Exception as e:
        print(f"Traffic error for {city}: {e}")
        return None

def web_search(query: str) -> str:
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=3)]
        if not results:
            return ""
        return "\n".join(r["body"] for r in results)
    except Exception as e:
        print(f"Web search error: {e}")
        return ""

def is_factual_query(text: str) -> bool:
    keywords = ["çfarë", "kush", "ku", "kur", "pse", "sa", "si", "formula", "trafik", "moti", "histori", "kush eshte", "sa kushton", "sa eshte", "si behet"]
    text_lower = text.lower()
    return any(word in text_lower for word in keywords) or len(text.split()) > 8

def get_edge_tts_url(text: str) -> str:
    voice = "sq-AL-NoraNeural"  # Zë femëror natyral shqip nga Microsoft Edge TTS
    text = text.replace("&", "dhe").replace("<", "").replace(">", "")  # Pastro për SSML
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
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        if r.status_code == 200:
            return "stream_url"  # Për ESP32/telefon – në praktikë mund ta ruash në S3 ose kthe stream
        else:
            print(f"TTS error: {r.status_code} {r.text}")
            return ""
    except Exception as e:
        print(f"TTS exception: {e}")
        return ""

def ask_groq(prompt: str) -> str:
    if not GROQ_API_KEY:
        raise HTTPException(500, "GROQ_API_KEY mungon")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    system = (
        "Ti je Luna, asistent inteligjent shqip shumë i saktë dhe logjik.\n"
        "Rregulla strikte:\n"
        "- Përgjigju vetëm me fakte të sakta dhe të verifikuara.\n"
        "- Nëse pyetja është për orë ose mot, përdor vetëm kontekstin ose kohën reale – mos shpik.\n"
        "- Nëse nuk je e sigurt, thuaj 'Nuk jam e sigurt' ose 'Më jep më shumë detaje'.\n"
        "- Përgjigje shumë të shkurtra, të drejtpërdrejta, pa fjalë të tepërta.\n"
        "- Mos përsërit pyetjen e përdoruesit.\n"
        "- Mos përmend burime, links ose 'sipas...'.\n"
        "- Nëse pyetja është e njëjtë disa herë, mos ndrysho përgjigjen pa arsye.\n"
        "- Për temperaturë/moti/trafik: përdor vetëm të dhënat e dhëna në kontekst.\n"
        "- Për 'play [këngë]': thuaj 'Link: https://youtube.com/results?search_query=[këngë]'\n"
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

    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Groq error: {e}")
        return "Gabim lidhje me AI – provo sërish"

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

    audio_url = get_edge_tts_url(answer)  # Zë femëror natyral shqip nga Microsoft Edge TTS

    return {"ok": True, "answer": answer, "audio_url": audio_url}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
