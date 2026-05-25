import os
import re
import asyncio
import httpx
from fastapi import FastAPI, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import pytz
from urllib.parse import quote

app = FastAPI()

# CORS i konfiguruar plotësisht për të lejuar çdo lloj lidhjeje hyrëse
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY    = os.getenv("LUNA_AI", "").strip()
WEATHER_API_KEY = os.getenv("Luna_weather", "").strip()
TZ              = pytz.timezone("Europe/Tirane")

current_audio_data: bytes = b""
audio_ready: bool = False
bisedat: Dict[str, List[Dict]] = {}
alarmet: List[Dict] = []
timerat: List[Dict] = []
perdoruesit: Dict[str, Dict] = {}

class AskBody(BaseModel):
    text: str
    device_id: str = "luna_default"
    emri: Optional[str] = None

QYTETET_MAP = {
    "tirana": "Tirana", "tiranë": "Tirana",
    "shkoder": "Shkodër", "shkodër": "Shkodër",
    "durres": "Durrës", "durrës": "Durrës",
    "vlore": "Vlorë", "vlorë": "Vlorë",
    "korce": "Korçë", "korçë": "Korçë",
    "elbasan": "Elbasan", "fier": "Fier",
    "berat": "Berat", "lushnje": "Lushnjë",
    "kavaje": "Kavajë", "pogradec": "Pogradec",
    "lezhe": "Lezhë", "kukes": "Kukës",
    "sarande": "Sarandë", "sarandë": "Sarandë",
    "gjirokaster": "Gjirokastër",
}

FJALE_BANALE = ["sigurisht", "natyrisht", "absolutisht", "me kënaqësi", "patjetër", "padyshim", "me gjithë qejf"]

def koha_tani() -> str:
    return datetime.now(TZ).strftime("%H:%M")

def data_sot() -> str:
    ditet  = ["E Hënë","E Martë","E Mërkurë","E Enjte","E Premte","E Shtunë","E Diel"]
    muajt  = ["Janar","Shkurt","Mars","Prill","Maj","Qershor","Korrik","Gusht","Shtator","Tetor","Nëntor","Dhjetor"]
    dt = datetime.now(TZ)
    return f"{ditet[dt.weekday()]}, {dt.day} {muajt[dt.month-1]} {dt.year}"

def pastro_pergjigje(text: str) -> str:
    for f in FJALE_BANALE:
        text = re.sub(f, "", text, flags=re.IGNORECASE)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[*#_~`]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

async def kerko_web(pyetja: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            headers = {"User-Agent": "LunaAI/5.0"}
            r = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": pyetja, "format": "json", "no_html": "1", "skip_disambig": "1"},
                headers=headers
            )
            data = r.json()
            rezultate = []
            if data.get("AbstractText"):
                rezultate.append(data["AbstractText"][:400])
            if data.get("Answer"):
                rezultate.append(str(data["Answer"]))
            if rezultate:
                return " ".join(rezultate[:2])
            return ""
    except Exception:
        return ""

async def duhet_kerkuar(pergjigja: str) -> bool:
    fraza = ["nuk kam informacion", "nuk di", "nuk mund të", "nuk e di", "nuk jam i sigurt", "knowledge cutoff"]
    return any(f in pergjigja.lower() for f in fraza)

async def merre_motin(qyteti: str = "Tirana") -> str:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": f"{qyteti},AL", "appid": WEATHER_API_KEY, "units": "metric", "lang": "sq"}
            )
            d = r.json()
            temp = round(d["main"]["temp"])
            pershk = d["weather"][0]["description"]
            return f"Moti në {qyteti} është {temp} gradë me {pershk}."
    except Exception:
        return "Nuk arrita ta marr motin për momentin."

async def merre_rrugën(origjina: str, destinacioni: str) -> str:
    try:
        orig_norm = QYTETET_MAP.get(origjina.lower().strip(), origjina.capitalize())
        dest_norm = QYTETET_MAP.get(destinacioni.lower().strip(), destinacioni.capitalize())
        async with httpx.AsyncClient(timeout=15) as client:
            headers = {"User-Agent": "LunaAI/5.0"}
            r1 = await client.get("https://nominatim.openstreetmap.org/search", params={"q": f"{orig_norm}, Albania", "format": "json", "limit": 1}, headers=headers)
            r2 = await client.get("https://nominatim.openstreetmap.org/search", params={"q": f"{dest_norm}, Albania", "format": "json", "limit": 1}, headers=headers)
            if not r1.json() or not r2.json(): return "Nuk i gjeta dot qytetet."
            lat1, lon1 = r1.json()[0]["lat"], r1.json()[0]["lon"]
            lat2, lon2 = r2.json()[0]["lat"], r2.json()[0]["lon"]
            route = await client.get(f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false")
            rd = route.json()
            distanca = rd["routes"][0]["distance"] / 1000
            koha_min = rd["routes"][0]["duration"] / 60
            return f"Nga {orig_norm} deri në {dest_norm} janë {distanca:.0f} kilometra. Udhëtimi zgjat {round(koha_min)} minuta."
    except Exception:
        return "Pati një problem gjatë llogaritjes së rrugës."

async def tts_edge(text: str) -> bool:
    global current_audio_data
    try:
        import edge_tts
        text_clean = pastro_pergjigje(text)
        if not text_clean:
            return False
        communicate = edge_tts.Communicate(text_clean, "sq-AL-AlbaNeural", rate="+0%", volume="+25%")
        data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                data += chunk["data"]
        if len(data) > 100:
            current_audio_data = data
            return True
        return False
    except Exception:
        return False

def detekto_intent(text: str) -> dict:
    t = text.lower().strip()
    if any(w in t for w in ["mot", "temperatur", "shi", "diell", "ftoht"]):
        qyteti = "Tirana"
        for k, v in QYTETET_MAP.items():
            if k in t: qyteti = v; break
        return {"lloj": "mot", "qyteti": qyteti}
    if any(w in t for w in ["sa është ora", "sa eshte ora", "ora tani"]):
        return {"lloj": "ora"}
    if any(w in t for w in ["çfarë date", "cfar date", "sa date", "sot është"]):
        return {"lloj": "data"}
    return {"lloj": "ai"}

def krijo_system_prompt(device_id: str) -> str:
    user = perdoruesit.get(device_id, {})
    emri = user.get("emri", "")
    qyteti = user.get("qyteti", "Tirana")
    return (
        f"Ti je Luna, një asistente AI shqiptare, jashtëzakonisht inteligjente, e mprehtë dhe koncize. "
        f"Ora aktuale: {koha_tani()}. Data sot: {data_sot()}. Qyteti: {qyteti}. Personi quhet: {emri}.\n\n"
        f"RREGULLAT:\n"
        f"1. Përgjigju VETËM në gjuhën shqipe.\n"
        f"2. Përgjigjet duhet të jene super të shkurtra (1-2 fjali maksimumi).\n"
        f"3. Ji natyrale dhe inteligjente si Alexa ose Siri.\n"
        f"4. MOS PËRDOR fjalë klishe si: 'sigurisht', 'natyrisht', 'me kënaqësi'.\n"
        f"5. Mos përdor asnjë emoji apo markdown pasi teksti do të lexohet automatikisht me zë."
    )

async def pyete_ai(mesazhet: list) -> str:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": mesazhet,
                    "temperature": 0.6,
                    "max_tokens": 120
                }
            )
            data = r.json()
            return pastro_pergjigje(data["choices"][0]["message"]["content"].strip())
    except Exception:
        return "Pata një problem me inteligjencën."

async def pergjigja_me_kerkime(device_id: str, teksti_user: str) -> str:
    bisedat[device_id].append({"role": "user", "content": teksti_user})
    p1 = await pyete_ai(bisedat[device_id])
    if await duhet_kerkuar(p1):
        info = await kerko_web(teksti_user)
        if info:
            m_reja = bisedat[device_id][:-1] + [{"role": "user", "content": f"Pyetja: {teksti_user}\nInfo interneti: {info}\nPërgjigju shkurt."}]
            p1 = await pyete_ai(m_reja)
    bisedat[device_id].append({"role": "assistant", "content": p1})
    return p1

@app.get("/")
def root():
    return {"status": "Luna AI Online"}

@app.post("/ask")
async def ask(body: AskBody):
    global audio_ready, current_audio_data
    if body.device_id not in bisedat:
        bisedat[body.device_id] = [{"role": "system", "content": krijo_system_prompt(body.device_id)}]

    intent = detekto_intent(body.text)
    pergjigja = ""

    if intent["lloj"] == "mot": pergjigja = await merre_motin(intent["qyteti"])
    elif intent["lloj"] == "ora": pergjigja = f"Ora është {koha_tani()}."
    elif intent["lloj"] == "data": pergjigja = f"Sot është {data_sot()}."
    else: pergjigja = await pergjigja_me_kerkime(body.device_id, body.text)

    audio_ready = False
    current_audio_data = b""
    ok = await tts_edge(pergjigja)
    if ok:
        audio_ready = True

    return {"answer": pergjigja, "audio_ok": ok}

@app.get("/get_audio")
async def get_audio():
    global current_audio_data
    if current_audio_data and len(current_audio_data) > 100:
        return Response(
            content=current_audio_data,
            media_type="audio/mpeg",
            headers={
                "Content-Length": str(len(current_audio_data)),
                "Accept-Ranges": "bytes",
                "Access-Control-Allow-Origin": "*"
            }
        )
    return Response(status_code=204)

@app.post("/done")
async def done():
    global audio_ready, current_audio_data
    audio_ready = False
    current_audio_data = b""
    return {"ok": True}
