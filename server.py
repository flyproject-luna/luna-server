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

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY       = os.getenv("LUNA_AI", "").strip()
WEATHER_API_KEY    = os.getenv("Luna_weather", "").strip()
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
TZ                 = pytz.timezone("Europe/Tirane")

# Përdorim zërin premium femëror "Rachel" (21m00Tcm4TlvDq8ikWAM) që flet shqip si njeri i vërtetë
VOICE_ID = "21m00Tcm4TlvDq8ikWAM" 

bisedat: Dict[str, List[Dict]] = {}
perdoruesit: Dict[str, Dict] = {}

class AskBody(BaseModel):
    text: str
    device_id: str = "luna_default"
    emri: Optional[str] = None

FJALE_BANALE = ["sigurisht", "natyrisht", "absolutisht", "me kënaqësi", "patjetër", "padyshim", "me gjithë qejf"]

def koha_tani() -> str:
    return datetime.now(TZ).strftime("%H:%M")

def data_sot() -> str:
    ditet  = ["E Hënë","E Martë","E Mërkurë","E Enjte","E Premte","E Shtunë","E Diel"]
    muajt  = ["Janar","Shkurt","Mars","Prill","Maj","Qershor","Korrik","Gusht","Shtator","Tetor","Nëntor","Dimër"]
    dt = datetime.now(TZ)
    return f"{ditet[dt.weekday()]} {dt.day} {muajt[dt.month-1]}"

def pastro_pergjigje(text: str) -> str:
    for f in FJALE_BANALE:
        text = re.sub(f, "", text, flags=re.IGNORECASE)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[*#_~`]', '', text)
    return re.sub(r'\s+', ' ', text).strip()

async def tts_elevenlabs_base64(text: str) -> str:
    try:
        text_clean = pastro_pergjigje(text)
        if not text_clean: return ""
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        data = {
            "text": text_clean,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=data, headers=headers)
            if response.status_code == 200:
                return base64.b64encode(response.content).decode('utf-8')
            else:
                print(f"Gabim ElevenLabs: {response.text}")
                return ""
    except Exception as e:
        print(f"Gabim TTS: {e}")
        return ""

async def pyete_ai(mesazhet: list) -> str:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": mesazhet, "temperature": 0.5, "max_tokens": 100}
            )
            return pastro_pergjigje(r.json()["choices"][0]["message"]["content"].strip())
    except Exception:
        return "Problem me inteligjencën."

@app.post("/ask")
async def ask(body: AskBody):
    if body.device_id not in bisedat:
        bisedat[body.device_id] = [{
            "role": "system", 
            "content": f"Ti je Luna, një asistente AI shqiptare, inteligjente dhe super koncize. Përgjigju vetëm shqip, me 1 ose maksimalisht 2 fjali të shkurtra. Mos përdor asnjëherë emoji apo markdown."
        }]

    bisedat[body.device_id].append({"role": "user", "content": body.text})
    pergjigja = await pyete_ai(bisedat[body.device_id])
    bisedat[body.device_id].append({"role": "assistant", "content": pergjigja})

    # Gjenerohet zëri njerëzor premium
    audio_base64 = await tts_elevenlabs_base64(pergjigja)

    return {
        "answer": pergjigja,
        "audio": audio_base64
    }
