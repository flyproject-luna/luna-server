import os
import requests
from gtts import gTTS
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional, Dict, List

app = FastAPI()

# --- KONFIGURIMI ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
MODEL_AI = "llama-3.3-70b-versatile"

# Ruajtja e bisedave (Memoria e Lunës)
bisedat: Dict[str, List[Dict]] = {}

class AskBody(BaseModel):
    text: str
    device_id: Optional[str] = "web_user"

# Funksioni për të marrë të dhënat kontekstuale
def merr_kontekstin():
    ora_shqiperi = datetime.utcnow() + timedelta(hours=1)
    koha = ora_shqiperi.strftime("%H:%M")
    data = ora_shqiperi.strftime("%d/%m/%Y")
    
    moti = "Moti: Tirana, 14°C, vrenjtur." # Default
    if OPENWEATHER_API_KEY:
        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?q=Tirana&appid={OPENWEATHER_API_KEY}&units=metric&lang=sq"
            r = requests.get(url, timeout=2).json()
            moti = f"Tiranë: {r['main']['temp']}°C, {r['weather'][0]['description']}."
        except: pass
    return koha, data, moti

# --- FAQA KRYESORE (DASHBOARD) ---
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
            .chat-container { width: 90%; max-width: 450px; background: #1e293b; padding: 30px; border-radius: 24px; box-shadow: 0 20px 50px rgba(0,0,0,0.5); border: 1px solid #334155; text-align: center; }
            h1 { color: #38bdf8; margin-bottom: 5px; font-size: 28px; }
            .subtitle { color: #94a3b8; font-size: 14px; margin-bottom: 25px; }
            input { width: 100%; padding: 18px; border-radius: 15px; border: 2px solid #334155; background: #0f172a; color: white; font-size: 16px; box-sizing: border-box; outline: none; transition: 0.3s; }
            input:focus { border-color: #38bdf8; box-shadow: 0 0 10px rgba(56, 189, 248, 0.2); }
            button { width: 100%; margin-top: 20px; padding: 18px; border-radius: 15px; border: none; background: #0284c7; color: white; font-weight: bold; font-size: 16px; cursor: pointer; transition: 0.2s; }
            button:hover { background: #0ea5e9; transform: translateY(-2px); }
            #luna-response { margin-top: 25px; font-style: italic; color: #38bdf8; line-height: 1.5; min-height: 40px; border-top: 1px solid #334155; padding-top: 15px; }
        </style>
    </head>
    <body>
        <div class="chat-container">
            <h1>Luna AI 🎙️</h1>
            <div class="subtitle">Lidhu me Havit M3 dhe shkruaj pyetjen</div>
            <input type="text" id="query" placeholder="Pyet diçka..." onkeypress="if(event.key==='Enter') pyet()">
            <button onclick="pyet()">DËRGO MESAZHIN</button>
            <div id="luna-response">Luna është gati të të dëgjojë.</div>
        </div>
        <audio id="audioPlayer" style="display:none"></audio>

        <script>
            async function pyet() {
                const input = document.getElementById('query');
                const resp = document.getElementById('luna-response');
                const player = document.getElementById('audioPlayer');
                const txt = input.value;

                if(!txt) return;

                resp.innerText = "Luna po mendohet...";
                input.value = "";

                try {
                    const response = await fetch('/ask', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({text: txt, device_id: 'mobile_phone'})
                    });

                    const data = await response.json();
                    resp.innerText = data.answer;

                    // Luaj zërin femëror automatikisht
                    player.src = '/get_audio?t=' + new Date().getTime();
                    player.play();
                } catch (e) {
                    resp.innerText = "Gabim: Serveri nuk po përgjigjet.";
                }
            }
        </script>
    </body>
    </html>
    """

# --- LOGJIKA E AI DHE ZËRIT ---
@app.post("/ask")
async def ask(body: AskBody):
    koha, data, moti = merr_kontekstin()
    
    # Krijo memorien e bisedës nëse nuk ekziston
    if body.device_id not in bisedat:
        bisedat[body.device_id] = [{
            "role": "system", 
            "content": f"Ti je Luna, asistente inteligjente dhe e embel. Sot eshte {data}, ora {koha}. {moti}. Pergjigju shkurter, me takt dhe ne gjuhen shqipe."
        }]

    bisedat[body.device_id].append({"role": "user", "content": body.text})
    
    # Thirrja te Groq
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL_AI, 
        "messages": bisedat[body.device_id], 
        "temperature": 0.7,
        "max_tokens": 150
    }
    
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        pergjigja = r.json()["choices"][0]["message"]["content"].strip()
        
        # Shto te memoria
        bisedat[body.device_id].append({"role": "assistant", "content": pergjigja})
        
        # Gjenero audion femërore (gTTS)
        tts = gTTS(text=pergjigja, lang='sq', slow=False)
        tts.save("luna_voice.mp3")
        
        return {"answer": pergjigja}
    except Exception as e:
        return {"answer": "Më fal, por truri im pati një problem të vogël teknik."}

@app.get("/get_audio")
async def get_audio():
    return FileResponse("luna_voice.mp3", media_type="audio/mpeg")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
