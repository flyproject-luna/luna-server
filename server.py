import os
import asyncio
import httpx
import json
import re
from fastapi import FastAPI, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import datetime, timedelta

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── API KEYS ───────────────────────────────────────────────
GROQ_API_KEY       = os.getenv("LUNA_AI", "").strip()
WEATHER_API_KEY    = os.getenv("Luna_weather", "").strip()

# ─── STATE ──────────────────────────────────────────────────
current_audio_data: bytes = b""
audio_ready: bool = False
bisedat: Dict[str, List[Dict]] = {}
alarmet: List[Dict] = []
timerat: List[Dict] = []

# ─── MODELET PYDANTIC ────────────────────────────────────────
class AskBody(BaseModel):
    text: str
    device_id: str = "luna_default"

# ════════════════════════════════════════════════════════════
#  FUNKSIONET NDIHMËSE
# ════════════════════════════════════════════════════════════

async def merre_motin(qyteti: str = "Tirana") -> str:
    """Mot live nga OpenWeatherMap"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={
                    "q": qyteti,
                    "appid": WEATHER_API_KEY,
                    "units": "metric",
                    "lang": "sq"
                }
            )
            d = r.json()
            temp      = d["main"]["temp"]
            ndjesia   = d["main"]["feels_like"]
            pershkrim = d["weather"][0]["description"]
            lageshti  = d["main"]["humidity"]
            era       = d["wind"]["speed"]
            return (
                f"Moti në {qyteti}: {temp:.0f}°C (ndihet si {ndjesia:.0f}°C), "
                f"{pershkrim}, lagështi {lageshti}%, erë {era} m/s."
            )
    except Exception as e:
        print(f"Gabim mot: {e}")
        return "Moti nuk është i disponueshëm tani."


async def merre_rrugën(origjina: str, destinacioni: str) -> str:
    """Distanca dhe kohë udhëtimi falas me OSRM"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            headers = {"User-Agent": "LunaAI/1.0"}

            r1 = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": f"{origjina}, Shqipëri", "format": "json", "limit": 1},
                headers=headers
            )
            r2 = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": f"{destinacioni}, Shqipëri", "format": "json", "limit": 1},
                headers=headers
            )

            loc1 = r1.json()
            loc2 = r2.json()

            if not loc1 or not loc2:
                return f"Nuk gjeta vendndodhjet për {origjina} ose {destinacioni}."

            lat1, lon1 = loc1[0]["lat"], loc1[0]["lon"]
            lat2, lon2 = loc2[0]["lat"], loc2[0]["lon"]

            route = await client.get(
                f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}",
                params={"overview": "false"}
            )
            rd = route.json()
            distanca_km = rd["routes"][0]["distance"] / 1000
            koha_min    = rd["routes"][0]["duration"] / 60

            if koha_min < 60:
                koha_str = f"{koha_min:.0f} minuta"
            else:
                ore  = int(koha_min // 60)
                mins = int(koha_min % 60)
                koha_str = f"{ore} orë e {mins} minuta"

            return (
                f"Nga {origjina} te {destinacioni}: "
                f"{distanca_km:.1f} km, afërsisht {koha_str} me makinë."
            )
    except Exception as e:
        print(f"Gabim rrugë: {e}")
        return "Nuk mund të gjej rrugën tani."


async def tts_edge(text: str) -> bool:
    """TTS falas me edge-tts - zë shqip AlbaNeural"""
    global current_audio_data
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, "sq-AL-AlbaNeural")
        data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                data += chunk["data"]
        current_audio_data = data
        return True
    except Exception as e:
        print(f"Gabim edge TTS: {e}")
        return False


def detekto_intent(text: str) -> dict:
    """Detekton çfarë dëshiron useri"""
    t = text.lower()

    if any(w in t for w in ["mot", "temperature", "shi", "diell", "ftohtë", "nxehtë", "lagështi", "temperatur"]):
        qyteti = "Tirana"
        for q in ["shkodër", "shkoder", "vlorë", "vlore", "durrës", "durres", "korçë", "korce", "gjirokastër", "elbasan", "fier", "berat"]:
            if q in t:
                qyteti = q.capitalize()
                break
        return {"lloj": "mot", "qyteti": qyteti}

    if any(w in t for w in ["rrugë", "rruge", "trafik", "distanc", "sa kohë", "sa kohe", "makine", "makinë", "shkoj nga", "nga ", " te ", " deri"]):
        return {"lloj": "rruge", "text": text}

    if any(w in t for w in ["sa është ora", "sa eshte ora", "çfarë ore", "cfar ore", "ora tani", "sa orë"]):
        return {"lloj": "ora"}

    if any(w in t for w in ["çfarë date", "cfar date", "sa date", "cila ditë", "sot është", "sot eshte"]):
        return {"lloj": "data"}

    if any(w in t for w in ["alarm", "më zgjo", "me zgjo", "zgjom", "vendos alarm"]):
        return {"lloj": "alarm", "text": text}

    if any(w in t for w in ["timer", "kujto pas", "pas 5 minut", "pas 10 minut", "pas një ore", "pas nje ore"]):
        return {"lloj": "timer", "text": text}

    return {"lloj": "ai"}


def krijo_system_prompt(moti: str, koha: str) -> str:
    alarmet_aktiv = [a for a in alarmet if a["aktiv"]]
    return (
        f"Ti je Luna, asistentja inteligjente shqiptare me zë të ëmbël dhe personalitet të ngrohtë. "
        f"Koha aktuale: {koha}. {moti} "
        f"Alarmet aktive: {len(alarmet_aktiv)}. "
        "Rregullat e tua:\n"
        "1. Përgjigju GJITHMONË në shqip, shkurt dhe qartë (max 3 fjali).\n"
        "2. Je miqësore, ngrohtë dhe ndihmëse si një shoqe e vërtetë.\n"
        "3. Kur jep receta, listo ingredientet shkurt.\n"
        "4. Kur jep rrugë, thuaj distancën dhe kohën.\n"
        "5. Mos përdor emoji të shumta - vetëm kur duhet.\n"
        "6. Je e ndërtuar nga një djalë shqiptar me pasion për teknologji.\n"
        "7. Emri yt është Luna dhe jeton në një pajisje fizike të bukur."
    )


async def pyete_ai(mesazhet: list, text: str) -> str:
    """Pyetje te Groq AI - i shpejtë dhe falas"""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": mesazhet,
                    "temperature": 0.75,
                    "max_tokens": 300
                }
            )
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Gabim AI: {e}")
        return "Më fal, nuk mund të përgjigjem tani. Provo përsëri!"


# ════════════════════════════════════════════════════════════
#  ENDPOINTS
# ════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {"status": "Luna AI është aktive! 🌙", "version": "2.0"}


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """STT me Groq Whisper - audio → tekst shqip"""
    try:
        audio_bytes = await audio.read()
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={"file": (audio.filename or "audio.wav", audio_bytes, "audio/wav")},
                data={"model": "whisper-large-v3", "language": "sq", "response_format": "json"}
            )
            teksti = r.json().get("text", "").strip()
            return {"text": teksti}
    except Exception as e:
        return {"text": "", "error": str(e)}


@app.post("/ask")
async def ask(body: AskBody):
    global audio_ready, current_audio_data

    moti_live = await merre_motin()
    koha_live = datetime.now().strftime("%d/%m/%Y %H:%M")

    if body.device_id not in bisedat:
        bisedat[body.device_id] = [
            {"role": "system", "content": krijo_system_prompt(moti_live, koha_live)}
        ]
    else:
        bisedat[body.device_id][0]["content"] = krijo_system_prompt(moti_live, koha_live)

    intent = detekto_intent(body.text)
    pergjigja = ""

    if intent["lloj"] == "mot":
        pergjigja = await merre_motin(intent["qyteti"])

    elif intent["lloj"] == "rruge":
        t = body.text.lower()
        match = re.search(r"nga\s+(.+?)\s+(?:te|deri|tek)\s+(.+?)(?:\s+me makine|\s+me makinë|$)", t)
        if match:
            origjina = match.group(1).strip()
            dest     = match.group(2).strip()
            pergjigja = await merre_rrugën(origjina, dest)
        else:
            bisedat[body.device_id].append({"role": "user", "content": body.text})
            pergjigja = await pyete_ai(bisedat[body.device_id], body.text)
            bisedat[body.device_id].append({"role": "assistant", "content": pergjigja})

    elif intent["lloj"] == "ora":
        ora_tani = datetime.now().strftime("%H:%M")
        pergjigja = f"Ora tani është {ora_tani}."

    elif intent["lloj"] == "data":
        ditet = ["E Hënë", "E Martë", "E Mërkurë", "E Enjte", "E Premte", "E Shtunë", "E Diel"]
        dita  = ditet[datetime.now().weekday()]
        data_sot = datetime.now().strftime("%d/%m/%Y")
        pergjigja = f"Sot është {dita}, {data_sot}."

    elif intent["lloj"] == "alarm":
        match = re.search(r"(\d{1,2})[:\.](\d{2})", body.text)
        if match:
            ora_alarm = f"{match.group(1).zfill(2)}:{match.group(2)}"
            alarmet.append({"ora": ora_alarm, "etiketa": "Alarm", "aktiv": True})
            pergjigja = f"Alarmi u vendos për orën {ora_alarm}. Do të të zgjoj unë!"
        else:
            pergjigja = "Më thuaj orën e saktë për alarmin, për shembull: vendos alarm në 07:30."

    elif intent["lloj"] == "timer":
        match = re.search(r"(\d+)\s*(minut|sekond|orë|ore)", body.text.lower())
        if match:
            sasia  = int(match.group(1))
            njesia = match.group(2)
            if "sekond" in njesia:
                sekonda = sasia
            elif "minut" in njesia:
                sekonda = sasia * 60
            else:
                sekonda = sasia * 3600
            fund = datetime.now() + timedelta(seconds=sekonda)
            timerat.append({"fund": fund.isoformat(), "sekonda": sekonda})
            pergjigja = f"Timer vendosur për {sasia} {njesia}. Do të të njoftoj kur të mbarojë!"
        else:
            pergjigja = "Sa minuta të vendos timerin? Thuaj për shembull: vendos timer 10 minuta."

    else:
        bisedat[body.device_id].append({"role": "user", "content": body.text})
        pergjigja = await pyete_ai(bisedat[body.device_id], body.text)
        bisedat[body.device_id].append({"role": "assistant", "content": pergjigja})

        if len(bisedat[body.device_id]) > 21:
            bisedat[body.device_id] = [bisedat[body.device_id][0]] + bisedat[body.device_id][-20:]

    audio_ready = False
    current_audio_data = b""
    ok = await tts_edge(pergjigja)
    if ok:
        audio_ready = True

    return {"answer": pergjigja, "intent": intent["lloj"]}


@app.get("/status")
async def status():
    return {"audio_ready": audio_ready, "ka_audio": len(current_audio_data) > 0}


@app.get("/get_audio")
async def get_audio():
    if current_audio_data:
        return Response(content=current_audio_data, media_type="audio/mpeg")
    return Response(status_code=204)


@app.post("/done")
async def done():
    global audio_ready, current_audio_data
    audio_ready = False
    current_audio_data = b""
    return {"ok": True}


@app.get("/alarmet")
async def get_alarmet():
    return {"alarmet": alarmet, "timerat": timerat}


@app.delete("/alarm/{index}")
async def fshi_alarmin(index: int):
    if 0 <= index < len(alarmet):
        alarmet.pop(index)
        return {"ok": True}
    return {"ok": False, "error": "Index i gabuar"}


@app.get("/health")
async def health():
    return {
        "status": "aktive",
        "groq": bool(GROQ_API_KEY),
        "weather": bool(WEATHER_API_KEY),
        "alarmet": len(alarmet),
        "timerat": len(timerat)
    }
