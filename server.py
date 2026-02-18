import os
import asyncio
import requests
import edge_tts
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional, Dict, List

app = FastAPI()

# --- KONFIGURIMI ---
# Sigurohu që i ke vendosur te Settings -> Variables në Railway
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MODEL_AI = "llama-3.1-8b-instant"

audio_ready = False
bisedat: Dict[str, List[Dict]] = {}

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

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <head><title>Luna AI</title><meta name="viewport" content="width=device-width, initial-scale=1"></head>
        <body style="font-family:sans-serif; background:#0f172a; color:white; text-align:center; padding:50px;">
            <h1>Luna AI 🎙️</h1>
            <input type="text" id="msg" style="padding:15px; width:80%; border-radius:10px; border:none; font-size:16px;">
            <br><br>
            <button onclick="pyet()" style="padding:15px 30px; border-radius:10px; background:#38bdf8; border:none; font-weight:bold; cursor:pointer;">DËRGO</button>
            <div id="status" style="margin-top:20px; color:#38bdf8;">Lidhur me ESP32 & Havit M3.</div>
            <script>
                async function pyet() {
                    const input = document.getElementById('msg');
                    const status = document.getElementById('status');
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
                    } catch (e) { status.innerText = "Gabim ne server."; }
                }
            </script>
        </body>
    </html>
    """

@app.post("/ask")
async def ask(body: AskBody):
    global audio_ready
    if body.device_id not in bisedat:
        bisedat[body.device_id] = [{"role": "system", "content": "Ti je Luna, asistente femer. Fol shqip dhe shkurt."}]
    
    bisedat[body.device_id].append({"role": "user", "content": body.text})
    
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": MODEL_AI, "messages": bisedat[body.device_id]}
    
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        pergjigja = r.json()["choices"][0]["message"]["content"].strip()
        
        if await gjenero_ze_femer(pergjigja):
            audio_ready = True
            
        return {"answer": pergjigja}
    except Exception as e:
        return {"answer": "Error gjate bisedes."}

@app.get("/status")
async def get_status():
    global audio_ready
    return {"ready": audio_ready}

@app.get("/get_audio")
async def get_audio():
    return FileResponse("luna_voice.mp3")

@app.get("/done")
async def set_done():
    global audio_ready
    audio_ready = False
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
