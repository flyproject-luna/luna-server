import os
import requests
from gtts import gTTS
from fastapi import FastAPI
from fastapi.responses import FileResponse
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional, Dict, List

app = FastAPI()
bisedat: Dict[str, List[Dict]] = {}

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
MODEL_AI = "llama-3.3-70b-versatile"

class AskBody(BaseModel):
    text: str
    device_id: Optional[str] = "unknown"

def merr_kontekstin():
    ora_shqiperi = datetime.utcnow() + timedelta(hours=1)
    koha = ora_shqiperi.strftime("%H:%M")
    moti = "Moti: Tirane, 14°C, vrenjtur." # Default nese API deshton
    if OPENWEATHER_API_KEY:
        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?q=Tirana&appid={OPENWEATHER_API_KEY}&units=metric&lang=sq"
            r = requests.get(url, timeout=2).json()
            moti = f"Tirane: {r['main']['temp']}°C, {r['weather'][0]['description']}."
        except: pass
    return koha, moti

@app.post("/ask")
async def ask(body: AskBody):
    koha, moti = merr_kontekstin()
    
    if body.device_id not in bisedat:
        bisedat[body.device_id] = [{
            "role": "system", 
            "content": f"Ti je Luna, nje asistente femer e embel dhe inteligjente. Ora: {koha}. {moti}. Pergjigju shkurter, paster dhe me takt."
        }]

    bisedat[body.device_id].append({"role": "user", "content": body.text})
    
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": MODEL_AI, "messages": bisedat[body.device_id], "temperature": 0.6}
    
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        pergjigja = r.json()["choices"][0]["message"]["content"].strip()
        
        # Gjenero zerin femeror (Shqip)
        tts = gTTS(text=pergjigja, lang='sq', slow=False)
        tts.save("luna_voice.mp3")
        
        return {"answer": pergjigja}
    except Exception as e:
        return {"answer": "Ndodhi nje gabim ne lidhje."}

@app.get("/get_audio")
async def get_audio():
    return FileResponse("luna_voice.mp3", media_type="audio/mpeg")
