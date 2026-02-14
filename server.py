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
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
MODEL_AI = "llama-3.3-70b-versatile"

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
    moti = "Moti: Tiranë, 14°C, vrenjtur."
    if OPENWEATHER_API_KEY:
        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?q=Tirana&appid={OPENWEATHER_API_KEY}&units=metric&lang=sq"
            r = requests.get(url, timeout=2).json()
            moti = f"Tiranë: {r['main']['temp']}°C, {r['weather'][0]['description']}."
        except: pass
    return koha, data, moti

# --- FUNKSIONI I ZERIT (Edge-TTS Falas) ---
async def gjenero_ze_femer(text):
    # Përdorim zërin Alba që është shumë natyral
    communicate = edge_tts.Communicate(text, "sq-AL-AlbaNeural")
    await communicate.save("luna_voice.mp3")

# --- FAQJA WEB (Kontrolli nga Telefoni) ---
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!DOCTYPE html>
    <html lang="sq">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>LUNA AI - Kontrolli</title>
        <style>
            body { font-family: 'Segoe UI', sans-serif; background: #0f172a; color: white; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; }
            .chat-box { width: 90%; max-width: 450px; background: #1e293b; padding: 30px; border-radius: 24px; box-shadow: 0 20px 50px rgba(0,0,0,0.5); border: 1px solid #334155; text-align: center; }
            h1 { color: #38bdf8; font-size: 28px; margin-bottom: 5px; }
            .subtitle { color: #94a3b8; font-size: 14px; margin-bottom: 25px; }
            input { width: 100%; padding: 18px; border-radius: 15px; border: 2px solid #334155; background: #0f172a; color: white; font-size: 16px; box-sizing: border-box; outline: none; transition: 0.3s; }
            input:focus { border-color: #38bdf8; }
            button { width: 100%; margin-top: 15px; padding: 18px; border-radius: 15px; border: none; background: #0284c7; color: white; font-weight: bold; font-size: 16px; cursor: pointer; }
            button:hover { background: #0ea5e9; }
            #status { margin-top: 25px; color: #38bdf8; font-style: italic; min-height: 40px; }
        </style>
    </head>
    <body>
        <div class="chat-box">
            <h1>Luna AI 🎙️</h1>
            <div class="subtitle">Boksi: Havit M3 | Zëri: Alba (Natyral)</div>
            <input type="text" id="msg" placeholder="Pyet Lunën..." onkeypress="if(event.key==='Enter') pyet()">
            <button onclick="pyet()">DËRGO</button>
            <div id="status">Gati për bisedë...</div>
        </div>
        <audio id="player" style="display:none"></audio>
        <script>
            async function pyet() {
                const input = document.getElementById('msg');
                const status = document.getElementById('status');
                const player = document.getElementById('player');
                const txt = input.value;
                if(!txt) return;
                status.innerText = "Luna po mendohet...";
                input.value = "";
                try {
                    const response = await fetch('/ask', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({text: txt, device_id: 'telefon_user'})
                    });
                    const data = await response.json();
                    status.innerText = data.answer;
                    player.src = '/get_audio?t=' + new Date().getTime();
                    player.play();
                } catch (e) { status.innerText = "Gabim lidhjeje."; }
            }
        </script>
    </body>
    </html>
    """

# --- LOGJIKA E PERGJIGJES ---
@app.post("/ask")
async def ask(body: AskBody):
    koha, data, moti = merr_kontekstin()
    
    if body.device_id not in bisedat:
        bisedat[body.device_id] = [{
            "role": "system", 
            "content": f"Ti je Luna, asistente femër inteligjente dhe shumë e ëmbël. Sot është {data}, ora {koha}. {moti}. Përgjigju shkurt, pastër dhe vetëm në shqip."
        }]

    bisedat[body.device_id].append({"role": "user", "content": body.text})
    
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": MODEL_AI, "messages": bisedat[body.device_id], "temperature": 0.7, "max_tokens": 150}
    
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        pergjigja = r.json()["choices"][0]["message"]["content"].strip()
        bisedat[body.device_id].append({"role": "assistant", "content": pergjigja})
        
        # Gjenero zërin natyral femëror
        await gjenero_ze_femer(pergjigja)
        
        return {"answer": pergjigja}
    except Exception as e:
        return {"answer": "Ndodhi një gabim teknik."}

@app.get("/get_audio")
async def get_audio():
    return FileResponse("luna_voice.mp3", media_type="audio/mpeg")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
