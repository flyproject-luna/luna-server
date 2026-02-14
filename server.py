import os
import requests
from gtts import gTTS
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional, List, Dict

app = FastAPI()
bisedat: Dict[str, List[Dict]] = {}

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
MODEL_AI = "llama-3.3-70b-versatile"

class AskBody(BaseModel):
    text: str
    device_id: str = "web_user"

# --- FAQJA E KONTROLLIT (HTML) ---
@app.get("/", response_class=HTMLResponse)
async def get_index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Luna AI Controller</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: sans-serif; background: #121212; color: white; text-align: center; padding: 20px; }
            input { width: 80%; padding: 15px; border-radius: 25px; border: none; margin-bottom: 20px; font-size: 16px; }
            button { background: #007bff; color: white; padding: 15px 30px; border: none; border-radius: 25px; cursor: pointer; font-size: 16px; }
            #response { margin-top: 30px; font-style: italic; color: #bbb; line-height: 1.6; }
            .status { color: #00ff00; font-size: 12px; margin-bottom: 10px; }
        </style>
    </head>
    <body>
        <h2>Luna AI</h2>
        <div class="status">Lidhur me Havit M3 (via Phone BT)</div>
        <input type="text" id="question" placeholder="Shkruaj pyetjen këtu...">
        <br>
        <button onclick="askLuna()">Dërgo Pyetjen</button>
        <p id="response"></p>
        <audio id="lunaAudio" style="display:none;"></audio>

        <script>
            async function askLuna() {
                const q = document.getElementById('question').value;
                const respDiv = document.getElementById('response');
                const audio = document.getElementById('lunaAudio');
                
                respDiv.innerText = "Luna po mendohet...";
                
                const response = await fetch('/ask', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({text: q, device_id: 'telefon_user'})
                });
                
                const data = await response.json();
                respDiv.innerText = data.answer;
                
                // Luaj audion
                audio.src = '/get_audio?t=' + list.getTime(); // timestamp per refresh
                audio.play();
                document.getElementById('question').value = "";
            }
        </script>
    </body>
    </html>
    """

@app.post("/ask")
async def ask(body: AskBody):
    # Logjika e Lunës (siç e kishim)
    luna_answer = ask_luna_logic(body.text, body.device_id) # Perdor funksionin qe kemi bere me pare
    
    # Gjenero Zërin
    tts = gTTS(text=luna_answer, lang='sq')
    tts.save("luna_voice.mp3")
    
    return {"answer": luna_answer}

@app.get("/get_audio")
async def get_audio():
    return FileResponse("luna_voice.mp3")

# Shto ketu funksionin ask_luna_logic qe ndertuam me pare...
