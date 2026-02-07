import os
import re
import requests
from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()

app = FastAPI(title="luna-server")

class AskReq(BaseModel):
    text: str
    city: str | None = "Tirana"
    lang: str | None = "sq"
    voice: str | None = "alloy"   # ndryshoje me vone sipas zërit që të pëlqen
    format: str | None = "mp3"    # mp3 është më i lehtë për browser

def _auth_headers():
    if not OPENAI_API_KEY:
        raise RuntimeError("Missing OPENAI_API_KEY")
    return {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

def safe_math(q: str) -> str | None:
    q2 = q.strip().replace("x", "*").replace("X", "*")
    if not re.fullmatch(r"[0-9\.\s\+\-\*\/\(\)\%]+", q2):
        return None
    try:
        val = eval(q2, {"__builtins__": {}}, {})
        if isinstance(val, (int, float)):
            if abs(val - round(val)) < 1e-12:
                return str(int(round(val)))
            return str(val)
    except Exception:
        return None
    return None

def openweather(city: str) -> str | None:
    if not OPENWEATHER_API_KEY:
        return None
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"}
    r = requests.get(url, params=params, timeout=15)
    if r.status_code != 200:
        return None
    j = r.json()
    temp = j["main"]["temp"]
    desc = j["weather"][0]["description"]
    return f"Moti në {city}: {temp:.0f}°C, {desc}."

def luna_answer(text: str, city: str, lang: str) -> str:
    # 1) math super shpejt
    m = safe_math(text)
    if m is not None:
        return m

    # 2) mot nëse pyet për mot
    low = text.lower()
    if any(w in low for w in ["mot", "temperatur", "shi", "diell", "weather"]):
        w = openweather(city or "Tirana")
        if w:
            return w

    # 3) LLM për gjithçka tjetër
    sys = (
        "Je Luna, asistente zanore në shqip. "
        "Përgjigju shkurt, e dashur, dhe shumë e dobishme. "
        "Nëse pyet për recetë: jep përbërësit + 4-6 hapa. "
        "Nëse pyet për këshillë (p.sh. çfarë të gatuaj sot): sugjero 2 opsione dhe pse. "
        "Mos përdor fjalë të pista."
    )

    payload = {
        "model": "gpt-4.1-mini",
        "input": [
            {"role": "system", "content": sys},
            {"role": "user", "content": text}
        ],
        "max_output_tokens": 220
    }

    r = requests.post("https://api.openai.com/v1/responses", headers=_auth_headers(), json=payload, timeout=45)
    if r.status_code >= 300:
        return "Pati problem me trurin. Provo prap."

    data = r.json()
    out = []
    for item in data.get("output", []):
        for c in item.get("content", []):
            if c.get("type") == "output_text" and "text" in c:
                out.append(c["text"])
    ans = ("".join(out)).strip()
    return ans or "S’e kapa tamam. Ma thuaj edhe një herë."

def tts(text: str, voice: str, fmt: str) -> bytes:
    payload = {
        "model": "gpt-4o-mini-tts",
        "voice": voice or "alloy",
        "format": fmt or "mp3",
        "input": text
    }
    r = requests.post("https://api.openai.com/v1/audio/speech", headers=_auth_headers(), json=payload, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"TTS error: {r.status_code} {r.text}")
    return r.content

@app.get("/health")
def health():
    return "ok"

@app.post("/ask-audio")
def ask_audio(req: AskReq):
    try:
        answer = luna_answer(req.text, req.city or "Tirana", req.lang or "sq")
        audio = tts(answer, req.voice or "alloy", req.format or "mp3")
        media = "audio/mpeg" if (req.format or "mp3").lower() == "mp3" else "audio/wav"
        return Response(content=audio, media_type=media, headers={"X-Luna-Text": answer[:200]})
    except Exception:
        return Response(content=b"", media_type="text/plain", status_code=500)
