import os
import asyncio
import requests
import edge_tts
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional, Dict, List

app = FastAPI()

# --- KONFIGURIMI I VARIABLAYE ---
# Sigurohu që i ke vendosur këto te Settings -> Variables në Railway
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
MODEL_AI = "llama3-8b-8192"  # Model më i shpejtë dhe i qëndrueshëm

# Memoria e bisedave
bisedat: Dict[str, List[Dict]] = {}

class AskBody(BaseModel):
    text: str
    device_id: Optional[str] = "web_user"

# Funksioni për kohën dhe motin
def merr_kontekstin():
    ora_shqiperi = datetime.utcnow() + timedelta(hours=1)
    koha = ora_shqiperi.strftime("%H:%M")
    data = ora_shqiperi.strftime("%d/%m/%Y")
    moti = "Moti: Tiranë, 14°C."
    if OPENWEATHER_API_KEY:
        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?q=Tirana&appid={OPENWEATHER_API_KEY}&units=metric&lang=sq"
            r = requests.get(url, timeout=2).json()
            moti = f"Tiranë: {r['main']['temp']}°C, {r['weather'][0]['description']}."
        except: pass
    return koha, data, moti

# --- FUNKSIONI I ZERIT (Edge-TTS Falas) ---
async def gjenero_ze_femer(text):
    try:
        communicate = edge_tts.Communicate(text, "sq-AL-AlbaNeural")
        await communicate.save("luna_voice.mp3")
        return True
    except:
        return False

# --- FAQJA WEB ---
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!DOCTYPE html>
    <html lang="sq">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>LUNA AI</title>
        <style>
            body { font-family: sans-serif; background: #0f172a; color: white; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; }
            .chat-box { width: 90%; max-width: 450px; background: #1e293b; padding: 30px; border-radius: 24px; text-align: center; border: 1px solid #334155; }
            h1 { color: #38bdf8; }
            input { width: 100%; padding: 15px; border-radius: 12px; border: none; margin-bottom: 15px; font-size: 16px; }
            button { width: 100%; padding: 15px; border-radius: 12px; border: none; background: #0284c7; color: white; font-weight: bold; cursor: pointer; }
            #status { margin-top: 20px; color: #38bdf8; font-style: italic; }
        </style>
    </head>
    <body>
        <div class="chat-box">
            <h1>Luna AI 🎙️</h1>
            <input type="text" id="msg" placeholder="Shkruaj këtu..." onkeypress="if(event.key==='Enter') pyet()">
            <button onclick="pyet()">DËRGO</button>
            <div id="status">Gati.</div>
        </div>
        <audio id="player" style="display:none"></audio>
        <script>
            async function pyet() {
                const input = document.getElementById('msg');
                const status = document.getElementById('status');
                const player = document.getElementById('player');
                if(!input.value) return;
                status.innerText = "Luna po mendohet...";
                try {
                    const response = await fetch('/ask', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({text: input.value})
                    });
                    const data = await response.json();
                    status.innerText = data.answer;
                    player.src = '/get_audio?t=' + new Date().getTime();
                    player.play();
                    input.value = "";
                } catch (e) { status.innerText = "Error në server."; }
            }
        </script>
    </body>
    </html>
    """

# --- LOGJIKA KRYESORE ---
@app.post("/ask")
async def ask(body: AskBody):
    koha, data, moti = merr_kontekstin()
    
    if body.device_id not in bisedat:
        bisedat[body.device_id] = [{
            "role": "system", 
            "content": f"Ti je Luna, asistente femër inteligjente. Sot është {data}, ora {koha}. {moti}. Përgjigju shkurt dhe shqip."
        }]

    bisedat[body.device_id].append({"role": "user", "content": body.text})
    
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": MODEL_AI, "messages": bisedat[body.device_id], "temperature": 0.7}
    
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        
        if r.status_code != 200:
            print(f"GROQ ERROR: {r.text}")
            return {"answer": "Më fal, truri im (Groq) nuk po përgjigjet. Kontrollo API Key."}

        pergjigja = r.json()["choices"][0]["message"]["content"].strip()
        bisedat[body.device_id].append({"role": "assistant", "content": pergjigja})
        
        await gjenero_ze_femer(pergjigja)
        return {"answer": pergjigja}
    except Exception as e:
        print(f"SYSTEM ERROR: {e}")
        return {"answer": "Ndodhi një gabim teknik."}

@app.get("/get_audio")
async def get_audio():
    return FileResponse("luna_voice.mp3")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
