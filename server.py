import os
import asyncio
import requests
import edge_tts
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional, Dict, List

app = FastAPI()

# --- KONFIGURIMI ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MODEL_AI = "llama-3.1-8b-instant"

# Variablat globale për sinkronizimin me ESP32
bisedat: Dict[str, List[Dict]] = {}
audio_ready = False

class AskBody(BaseModel):
    text: str
    device_id: Optional[str] = "web_user"

async def gjenero_ze_femer(text):
    try:
        communicate = edge_tts.Communicate(text, "sq-AL-AlbaNeural")
        await communicate.save("luna_voice.mp3")
        return True
    except Exception as e:
        print(f"Gabim TTS: {e}")
        return False

# --- NDËRFAQJA PËR TELEFONIN ---
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <head>
            <title>Luna AI - Kontrolli</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body { font-family: sans-serif; background: #0f172a; color: white; text-align: center; padding: 30px; }
                .box { background: #1e293b; padding: 25px; border-radius: 20px; border: 1px solid #334155; }
                input { width: 100%; padding: 15px; border-radius: 10px; border: none; margin: 15px 0; font-size: 16px; }
                button { width: 100%; padding: 15px; border-radius: 10px; background: #38bdf8; border: none; font-weight: bold; cursor: pointer; }
                #status { margin-top: 20px; color: #38bdf8; font-style: italic; }
            </style>
        </head>
        <body>
            <div class="box">
                <h1>Luna AI 🎙️</h1>
                <p>Zëri do të dalë te Havit M3 via ESP32</p>
                <input type="text" id="msg" placeholder="Shkruaj pyetjen këtu...">
                <button onclick="pyet()">DËRGO LUNËS</button>
                <div id="status">Gati.</div>
            </div>
            <script>
                async function pyet() {
                    const input = document.getElementById('msg');
                    const status = document.getElementById('status');
                    if(!input.value) return;
                    status.innerText = "Luna po mendohet...";
                    try {
                        const res = await fetch('/ask', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({text: input.value})
                        });
                        const data = await res.json();
                        status.innerText = data.answer;
                        input.value = "";
                    } catch (e) { status.innerText = "Gabim lidhjeje."; }
                }
            </script>
        </body>
    </html>
    """

# --- LOGJIKA E AI DHE STATUSIT ---
@app.post("/ask")
async def ask(body: AskBody):
    global audio_ready
    if body.device_id not in bisedat:
        bisedat[body.device_id] = [{"role": "system", "content": "Ti je Luna, asistente femër e ëmbël. Përgjigju shkurt në shqip."}]
    
    bisedat[body.device_id].append({"role": "user", "content": body.text})
    
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": MODEL_AI, "messages": bisedat[body.device_id]}
    
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        pergjigja = r.json()["choices"][0]["message"]["content"].strip()
        
        # Gjenerojmë audion
        if await gjenero_ze_femer(pergjigja):
            audio_ready = True # Lajmërojmë ESP32
            
        return {"answer": pergjigja}
    except Exception as e:
        return {"answer": "Gabim teknik."}

@app.get("/status")
async def get_status():
    global audio_ready
    return {"ready": audio_ready}

@app.get("/get_audio")
async def get_audio():
    if os.path.exists("luna_voice.mp3"):
        return FileResponse("luna_voice.mp3", media_type="audio/mpeg")
    return {"error": "Jo audio"}

@app.get("/done")
async def set_done():
    global audio_ready
    audio_ready = False
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
