import os
import re
import asyncio
import httpx
import base64
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import datetime
import pytz
import edge_tts

app = FastAPI()

# CORS plotësisht i hapur për të lejuar skedarin tënd HTML lokal
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY    = os.getenv("LUNA_AI", "").strip()
WEATHER_API_KEY = os.getenv("Luna_weather", "").strip()
TZ              = pytz.timezone("Europe/Tirane")

bisedat: Dict[str, List[Dict]] = {}
perdoruesit: Dict[str, Dict] = {}

class AskBody(BaseModel):
    text: str
    device_id: str = "luna_default"
    emri: Optional[str] = None

QYTETET_MAP = {
    "tirana": "Tirana", "tiranë": "Tirana",
    "shkoder": "Shkodër", "shkodër": "Shkodër",
    "durres": "Durrës", "durrës": "Durrës",
    "vlore": "Vlorë", "vlorë": "Vlorë",
    "korce": "Korçë", "korçë": "Korçë",
    "elbasan": "Elbasan", "fier": "Fier",
    "berat": "Berat", "lushnje": "Lushnjë",
}

FJALE_BANALE = ["sigurisht", "natyrisht", "absolutisht", "me kënaqësi", "patjetër", "padyshim", "me gjithë qejf"]

def koha_tani() -> str:
    return datetime.now(TZ).strftime("%H:%M")

def data_sot() -> str:
    ditet  = ["E Hënë","E Martë","E Mërkurë","E Enjte","E Premte","E Shtunë","E Diel"]
    muajt  = ["Janar","Shkurt","Mars","Prill","Maj","Qershor","Korrik","Gusht","Shtator","Tetor","Nëntor","Dhjetor"]
    dt = datetime.now(TZ)
    return f"{ditet[dt.weekday()]}, {dt.day} {muajt[dt.month-1]} {dt.year}"

def pastro_pergjigje(text: str) -> str:
    for f in FJALE_BANALE:
        text = re.sub(f, "", text, flags=re.IGNORECASE)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[*#_~`]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

async def kerko_web(pyetja: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            headers = {"User-Agent": "LunaAI/5.0"}
            r = await client.get("https://api.duckduckgo.com/", params={"q": pyetja, "format": "json", "no_html": "1"}, headers=headers)
            data = r.json()
            if data.get("AbstractText"): return data["AbstractText"][:400]
            return ""
    except Exception:
        return ""

async def duhet_kerkuar(pergjigja: str) -> bool:
    return any(f in pergjigja.lower() for f in ["nuk kam informacion", "nuk di", "nuk e di", "nuk jam i sigurt"])

async def merre_motin(qyteti: str = "Tirana") -> str:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get("https://api.openweathermap.org/data/2.5/weather", params={"q": f"{qyteti},AL", "appid": WEATHER_API_KEY, "units": "metric", "lang": "sq"})
            d = r.json()
            return f"Moti në {qyteti} është {round(d['main']['temp'])} gradë me {d['weather'][0]['description']}."
    except Exception:
        return "Nuk arrita ta marr motin."

# Funksioni i ri asinkron plotësisht i stabilizuar
async def tts_edge_base64(text: str) -> str:
    try:
        text_clean = pastro_pergjigje(text)
        if not text_clean: 
            return ""
        
        # Zëri premium i vajzës shqiptare
        communicate = edge_tts.Communicate(text_clean, "sq-AL-AlbaNeural", rate="+0%", volume="+25%")
        audio_bytes = b""
        
        # Grumbullimi i të dhënave në mënyrë të sigurt
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        
        if audio_bytes:
            print(f"Sukses! U gjeneruan {len(audio_bytes)} bytes audio.")
            return base64.b64encode(audio_bytes).decode('utf-8')
        
        print("Gabim: Nuk u gjenerua asnjë byte audio.")
        return ""
    except Exception as e:
        print(f"Gabim i rëndë në TTS: {e}")
        return ""

def detekto_intent(text: str) -> dict:
    t = text.lower().strip()
    if any(w in t for w in ["mot", "temperatur", "shi", "diell"]):
        qyteti = "Tirana"
        for k, v in QYTETET_MAP.items():
            if k in t: qyteti = v; break
        return {"lloj": "mot", "qyteti": qyteti}
    if any(w in t for w in ["sa është ora", "sa eshte ora", "ora tani"]): return {"lloj": "ora"}
    if any(w in t for w in ["çfarë date", "cfar date", "sa date"]): return {"lloj": "data"}
    return {"lloj": "ai"}

def krijo_system_prompt(device_id: str) -> str:
    user = perdoruesit.get(device_id, {})
    emri = user.get("emri", "")
    qyteti = user.get("qyteti", "Tirana")
    return (
        f"Ti je Luna, një asistente AI shqiptare, jashtëzakonisht inteligjente, e mprehtë dhe koncize. "
        f"Ora aktuale: {koha_tani()}. Data sot: {data_sot()}. Qyteti: {qyteti}. Personi quhet: {emri}.\n\n"
        f"RREGULLAT:\n"
        f"1. Përgjigju VETËM në gjuhën shqipe.\n"
        f"2. Përgjigjet duhet të jenë super të shkurtra (1-2 fjali maksimumi).\n"
        f"3. Ji natyrale dhe inteligjente si Alexa ose Siri.\n"
        f"4. MOS PËRDOR fjalë klishe si: 'sigurisht', 'natyrisht', 'me kënaqësi'.\n"
        f"5. Mos përdor asnjë emoji apo markdown pasi teksti do të lexohet automatikisht me zë."
    )

async def pyete_ai(mesazhet: list) -> str:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": mesazhet, "temperature": 0.6, "max_tokens": 120}
            )
            return pastro_pergjigje(r.json()["choices"][0]["message"]["content"].strip())
    except Exception:
        return "Pata një problem me inteligjencën."

async def pergjigja_me_kerkime(device_id: str, teksti_user: str) -> str:
    if device_id not in bisedat:
        bisedat[device_id] = [{"role": "system", "content": krijo_system_prompt(device_id)}]
        
    bisedat[device_id].append({"role": "user", "content": teksti_user})
    p1 = await pyete_ai(bisedat[device_id])
    if await duhet_kerkuar(p1):
        info = await kerko_web(teksti_user)
        if info:
            m_reja = bisedat[device_id][:-1] + [{"role": "user", "content": f"Pyetja: {teksti_user}\nInfo interneti: {info}\nPërgjigju shkurt."}]
            p1 = await pyete_ai(m_reja)
    bisedat[device_id].append({"role": "assistant", "content": p1})
    return p1

@app.get("/")
def root():
    return {"status": "Luna AI Stable AlbaNeural Voice Online"}

@app.post("/ask")
async def ask(body: AskBody):
    if body.device_id not in bisedat:
        bisedat[body.device_id] = [{"role": "system", "content": krijo_system_prompt(body.device_id)}]

    intent = detekto_intent(body.text)
    pergjigja = ""

    if intent["lloj"] == "mot": pergjigja = await merre_motin(intent["qyteti"])
    elif intent["lloj"] == "ora": pergjigja = f"Ora është {koha_tani()}."
    elif intent["lloj"] == "data": pergjigja = f"Sot është {data_sot()}."
    else: pergjigja = await pergjigja_me_kerkime(body.device_id, body.text)

    # Thirrja e funksionit të stabilizuar asinkron
    audio_base64 = await tts_edge_base64(pergjigja)

    return {
        "answer": pergjigja,
        "audio": audio_base64
    }
