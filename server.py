import os
import asyncio
import httpx
import edge_tts
from fastapi import FastAPI, Response
from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import datetime

app = FastAPI()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MODEL_AI = "llama-3.1-8b-instant"

current_audio_data = b""
audio_ready = False
bisedat: Dict[str, List[Dict]] = {}

# --- FUNKSIONI PËR MOTIN LIVE (FALAS) ---
async def merre_motin():
    try:
        async with httpx.AsyncClient() as client:
            # Koordinatat për Tiranën (mund t'i ndryshosh)
            r = await client.get("https://api.open-meteo.com/v1/forecast?latitude=41.3275&longitude=19.8189&current_weather=true")
            data = r.json()
            temp = data["current_weather"]["temperature"]
            return f"Moti tani: {temp}°C në Tiranë."
    except:
        return "Nuk mund ta shoh motin tani, por duket ditë e bukur!"

# --- PROMPT-I ME "SHPIRT" DHE INTELIGJENCË ---
def krijo_system_prompt(moti, koha):
    return (
        f"Ti je Luna, një asistente me shpirt dhe inteligjencë njerëzore. Koha aktuale: {koha}. {moti}. "
        "Je e programuar të jesh e dashur, e arsyeshme dhe të sillesh si një shoqe e vërtetë. "
        "Përgjigju shkurt, me emocion dhe përdor informacione reale. "
        "Nëse të kërkojnë batuta, receta ose ndihmë, bëje me qejf. "
        "Ti je Luna dhe jeton brenda një pajisjeje fizike që po ndërtohet me pasion."
    )

async def gjenero_ze_shqip(text):
    global current_audio_data
    try:
        # Zëri AlbaNeural është fiks zë femre shqiptar, i ëmbël dhe falas
        communicate = edge_tts.Communicate(text, "sq-AL-AlbaNeural")
        data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                data += chunk["data"]
        current_audio_data = data
        return True
    except Exception as e:
        print(f"Gabim TTS: {e}")
        return False

@app.post("/ask")
async def ask(body: AskBody):
    global audio_ready
    
    moti_live = await merre_motin()
    koha_live = datetime.now().strftime("%d/%m/%Y, %H:%M:%S")
    
    if body.device_id not in bisedat:
        bisedat[body.device_id] = [{"role": "system", "content": krijo_system_prompt(moti_live, koha_live)}]
    else:
        # Përditësojmë instruksionet e kohës në çdo sekondë që flasim
        bisedat[body.device_id][0]["content"] = krijo_system_prompt(moti_live, koha_live)
    
    bisedat[body.device_id].append({"role": "user", "content": body.text})
    
    async with httpx.AsyncClient() as client:
        payload = {
            "model": MODEL_AI, 
            "messages": bisedat[body.device_id],
            "temperature": 0.8
        }
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
        
        r = await client.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers)
        pergjigja = r.json()["choices"][0]["message"]["content"].strip()
        
        bisedat[body.device_id].append({"role": "assistant", "content": pergjigja})
        
        # Mbajmë memorien e bisedës vetëm për 10 mesazhet e fundit (për shpejtësi)
        if len(bisedat[body.device_id]) > 10:
            bisedat[body.device_id] = [bisedat[body.device_id][0]] + bisedat[body.device_id][-9:]

        if await gjenero_ze_shqip(pergjigja):
            audio_ready = True
            
        return {"answer": pergjigja}

# ... (Endpoint-et e tjerë /status, /get_audio, /done mbeten të njëjtë)
