# LUNA AI — ULTRA FUTURISTIC FULL SYSTEM

## SERVER — `server_v5.py`

```python
import os
import re
import asyncio
import httpx
import tempfile
import edge_tts
from fastapi import FastAPI, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import datetime
import pytz

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TZ = pytz.timezone("Europe/Tirane")

GROQ_API_KEY = os.getenv("LUNA_AI", "")

current_audio_data: bytes = b""

bisedat: Dict[str, List[Dict]] = {}

class AskBody(BaseModel):
    text: str
    device_id: str = "luna_device"


async def tts_edge(text: str):

    global current_audio_data

    try:

        communicate = edge_tts.Communicate(
            text,
            "sq-AL-AlbaNeural",
            rate="-12%",
            volume="+40%",
            pitch="-10Hz"
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            path = tmp.name

        await communicate.save(path)

        with open(path, "rb") as f:
            current_audio_data = f.read()

        os.remove(path)

        print("AUDIO READY", len(current_audio_data))

        return True

    except Exception as e:
        print("TTS ERROR", e)
        return False


async def pyete_ai(messages):

    async with httpx.AsyncClient(timeout=60) as client:

        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
                "temperature": 0.8,
                "max_tokens": 200
            }
        )

        data = r.json()

        return data["choices"][0]["message"]["content"]


@app.get("/")
async def root():
    return {"status": "Luna AI Online"}


@app.post("/ask")
async def ask(body: AskBody):

    global current_audio_data

    if body.device_id not in bisedat:

        bisedat[body.device_id] = [
            {
                "role": "system",
                "content": (
                    "Ti je Luna, nje asistente futuristike shqiptare. "
                    "Flet shkurt, bukur, embel dhe inteligjent. "
                    "Pergjigju gjithmone ne shqip."
                )
            }
        ]

    bisedat[body.device_id].append({
        "role": "user",
        "content": body.text
    })

    pergjigja = await pyete_ai(bisedat[body.device_id])

    bisedat[body.device_id].append({
        "role": "assistant",
        "content": pergjigja
    })

    await tts_edge(pergjigja)

    return {
        "ok": True,
        "answer": pergjigja
    }


@app.get("/get_audio")
async def get_audio():

    global current_audio_data

    if current_audio_data:

        return Response(
            content=current_audio_data,
            media_type="audio/mpeg"
        )

    return Response(status_code=204)


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):

    try:

        audio_bytes = await audio.read()

        async with httpx.AsyncClient(timeout=60) as client:

            r = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}"
                },
                files={
                    "file": ("audio.webm", audio_bytes, "audio/webm")
                },
                data={
                    "model": "whisper-large-v3",
                    "language": "sq"
                }
            )

            data = r.json()

            return {
                "text": data.get("text", "")
            }

    except Exception as e:

        return {
            "text": "",
            "error": str(e)
        }

