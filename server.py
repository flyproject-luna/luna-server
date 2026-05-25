import os
import re
import asyncio
import httpx
import base64
from fastapi import FastAPI, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import pytz
from urllib.parse import quote

app = FastAPI()

# CORS i hapur plotësisht që të lejojë skedarët lokalë HTML të komunikojnë pa bllokime
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
    return f"{ditet[dt.weekday()]} {dt.day} {muajt[dt.month-1]} {dt.year}"

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

            r2 = await client.get("https://sq.wikipedia.org/api/rest_v1/page/summary/" + quote(pyetja), headers=headers)
            if r2.status_code == 200:
                return r2.json().get("extract", "")[:400]
            return ""
    except Exception:
        return ""

async def duhet_kerkuar(pergjigja: str) -> bool:
    fraza = ["nuk kam informacion", "nuk di", "nuk mund të", "nuk e di", "nuk jam i sigurt", "training data", "knowledge cutoff"]
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
            loc1, loc2 = r1.json(), r2.json()
            if not loc1 or not loc2: return "Nuk i gjeta dot qytetet e kërkuara."
            lat1, lon1 = loc1[0]["lat"], loc1[0]["lon"]
            lat2, lon2 = loc2[0]["lat"], loc2[0]["lon"]
            route = await client.get(f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false")
            rd = route.json()
            if rd.get("code") != "Ok": return "Nuk munda të gjej një rrugë automobilistike."
            distanca = rd["routes"][0]["distance"] / 1000
            koha_min = rd["routes"][0]["duration"] / 60
            return f"Nga {orig_norm} deri në {dest_norm} janë {distanca:.0f} kilometra. Udhëtimi zgjat afërsisht {round(koha_min)} minuta."
    except Exception:
        return "Pati një problem gjatë llogaritjes së rrugës."

# TTS direkt me kthim bytes
async def gjenëro_tts_bytes(text: str) -> bytes:
    try:
        import edge_tts
        text_clean = pastro_pergjigje(text)
        if not text_clean:
            return b""
        communicate = edge_tts.Communicate(text_clean, "sq-AL-AlbaNeural", rate="+0%", volume="+25%")
        data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                data += chunk["data"]
        return data
    except Exception as e:
        print(f"Gabim te Edge TTS: {e}")
        return b""

def detekto_intent(text: str) -> dict:
    t = text.lower().strip()
    if any(w in t for w in ["mot", "temperatur", "shi", "diell", "ftoht", "nxeht"]):
        qyteti = "Tirana"
        for k, v in QYTETET_MAP.items():
            if k in t: qyteti = v; break
        return {"lloj": "mot", "qyteti": qyteti}
    if any(w in t for w in ["rrug", "trafik", "distanc", "sa koh", "sa kohe", "km", "makin"]):
        return {"lloj": "rruge", "text": text}
    if any(w in t for w in ["sa është ora", "sa eshte ora", "çfarë ore", "ora tani"]):
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
        f"2. Përgjigjet duhet të jenë super të shkurtra (1-2 fjali maksimumi). Mos shpjego gjëra që nuk pyeten.\n"
        f"3. Ji natyrale, e drejtpërdrejtë dhe inteligjente si Alexa ose Siri.\n"
        f"4. MOS PËRDOR fjalë klishe si: 'sigurisht', 'natyrisht', 'me kënaqësi', 'patjetër'.\n"
        f"5. Mos përdor asnjë emoji apo markdown (si yje apo vija) pasi teksti do të lexohet automatikisht me zë."
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
        return "Pata një problem me serverin e inteligjencës."

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
    if body.device_id not in bisedat:
        bisedat[body.device_id] = [{"role": "system", "content": krijo_system_prompt(body.device_id)}]

    intent = detekto_intent(body.text)
    pergjigja = ""

    if intent["lloj"] == "mot": pergjigja = await merre_motin(intent["qyteti"])
    elif intent["lloj"] == "ora": pergjigja = f"Ora është {koha_tani()}."
    elif intent["lloj"] == "data": pergjigja = f"Sot është e {data_sot()}."
    elif intent["lloj"] == "rruge":
        match = re.search(r"nga\s+([a-zëç\s]+?)\s+(?:te|deri|tek)\s+([a-zëç\s]+)", body.text.lower())
        if match: pergjigja = await merre_rrugën(match.group(1).strip(), match.group(2).strip())
        else: pergjigja = await pergjigja_me_kerkime(body.device_id, body.text)
    else:
        pergjigja = await pergjigja_me_kerkime(body.device_id, body.text)

    # Gjenerojmë audion direkt në moment
    audio_bytes = await gjenëro_tts_bytes(pergjigja)
    audio_base64 = ""
    if audio_bytes:
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

    return {
        "answer": pergjigja,
        "audio": audio_base64  # I dërgohet uebsajtit si string i enkriptuar që të luhet pa fetch tjetër
    }
