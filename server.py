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

# Merri keto nga Environment Variables ne Railway
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
MODEL_AI = "llama-3.3-70b-versatile"

class AskBody(BaseModel):
    text: str
    device_id: Optional[str] = "unknown"

@app.get("/")
async def root():
    return {"status": "Luna eshte online dhe gati!"}

@app.post("/ask")
async def ask(body: AskBody):
    # Logjika e Kohes
    ora_shqiperi = datetime.utcnow() + timedelta(hours=1)
    koha_sakt = ora_shqiperi.strftime("%H:%M")
    
    # Fillimi i Kontekstit
    if body.device_id not in bisedat:
        bisedat[body.device_id] = [{
            "role": "system", 
            "content": f"Ti je Luna, nje asistente femer e embel. Ora eshte {koha_sakt}. Fol shkurter dhe shqip."
        }]

    bisedat[body.device_id].append({"role": "user", "content": body.text})
    
    # Thirrja ne Groq
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": MODEL_AI, "messages": bisedat[body.device_id], "temperature": 0.7}
    
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        res_json = r.json()
        pergjigja = res_json["choices"][0]["message"]["content"].strip()
        
        # Krijo Zerin
        tts = gTTS(text=pergjigja, lang='sq')
        tts.save("luna_voice.mp3")
        
        return {"answer": pergjigja}
    except Exception as e:
        return {"answer": f"Gabim: {str(e)}"}

@app.get("/get_audio")
async def get_audio():
    return FileResponse("luna_voice.mp3")

if __name__ == "__main__":
    import uvicorn
    # Railway kerkon porten nga variabla PORT
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
