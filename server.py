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

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── API KEYS ────────────────────────────────────────────────
GROQ_API_KEY    = os.getenv("LUNA_AI", "").strip()
WEATHER_API_KEY = os.getenv("Luna_weather", "").strip()
TZ              = pytz.timezone("Europe/Tirane")

# ─── STATE ───────────────────────────────────────────────────
current_audio_data: bytes = b""
audio_ready: bool = False
bisedat: Dict[str, List[Dict]] = {}
alarmet: List[Dict] = []
timerat: List[Dict] = []
perdoruesit: Dict[str, Dict] = {}  # Ruan info per cdo user

# ─── MODELET ─────────────────────────────────────────────────
class AskBody(BaseModel):
    text: str
    device_id: str = "luna_default"
    emri: Optional[str] = None  # Emri i perdoruesit

class RegjistroBody(BaseModel):
    device_id: str
    emri: str
    qyteti: Optional[str] = "Tirana"

# ─── QYTETET SHQIPERI ────────────────────────────────────────
QYTETET_MAP = {
    "tirana": "Tirana", "tiranë": "Tirana",
    "shkoder": "Shkodër", "shkodër": "Shkodër",
    "durres": "Durrës", "durrës": "Durrës",
    "vlore": "Vlorë", "vlorë": "Vlorë",
    "korce": "Korçë", "korçë": "Korçë",
    "elbasan": "Elbasan",
    "fier": "Fier",
    "berat": "Berat",
    "gjirokaster": "Gjirokastër", "gjirokastër": "Gjirokastër",
    "lushnje": "Lushnjë",
    "kavaje": "Kavajë",
    "pogradec": "Pogradec",
    "lezhe": "Lezhë",
    "kukes": "Kukës",
    "permet": "Përmet",
    "sarande": "Sarandë", "sarandë": "Sarandë",
}

def koha_tani() -> str:
    return datetime.now(TZ).strftime("%H:%M")

def data_sot() -> str:
    ditet = ["E Hënë","E Martë","E Mërkurë","E Enjte","E Premte","E Shtunë","E Diel"]
    dt = datetime.now(TZ)
    muajt = ["Janar","Shkurt","Mars","Prill","Maj","Qershor",
             "Korrik","Gusht","Shtator","Tetor","Nëntor","Dhjetor"]
    return f"{ditet[dt.weekday()]}, {dt.day} {muajt[dt.month-1]} {dt.year}"

def koha_e_dites() -> str:
    ora = int(koha_tani().split(":")[0])
    if 5 <= ora < 12:   return "mirëmëngjes"
    if 12 <= ora < 17:  return "mirëdita"
    if 17 <= ora < 21:  return "mirëmbrëma"
    return "natën e mirë"

# ════════════════════════════════════════════════════════════
#  MOT
# ════════════════════════════════════════════════════════════
async def merre_motin(qyteti: str = "Tirana") -> str:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": f"{qyteti},AL", "appid": WEATHER_API_KEY,
                        "units": "metric", "lang": "sq"}
            )
            d = r.json()
            if d.get("cod") != 200:
                # Provo pa AL
                r = await client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={"q": qyteti, "appid": WEATHER_API_KEY,
                            "units": "metric", "lang": "sq"}
                )
                d = r.json()
            temp      = round(d["main"]["temp"])
            ndjesia   = round(d["main"]["feels_like"])
            pershkrim = d["weather"][0]["description"]
            lageshti  = d["main"]["humidity"]
            era       = d["wind"]["speed"]
            min_t     = round(d["main"]["temp_min"])
            max_t     = round(d["main"]["temp_max"])
            return (
                f"Moti në {qyteti} tani: {temp}°C, ndihet si {ndjesia}°C. "
                f"{pershkrim.capitalize()}. "
                f"Min {min_t}°C, max {max_t}°C, lagështi {lageshti}%, erë {era:.1f} m/s."
            )
    except Exception as e:
        print(f"Gabim mot: {e}")
        return f"Nuk mund të marr motin për {qyteti} tani."

# ════════════════════════════════════════════════════════════
#  RRUGA / TRAFIK
# ════════════════════════════════════════════════════════════
async def normalo_qytetin(emri: str) -> str:
    emri_l = emri.lower().strip()
    return QYTETET_MAP.get(emri_l, emri.capitalize())

async def merre_rrugën(origjina: str, destinacioni: str) -> str:
    try:
        orig_norm = await normalo_qytetin(origjina)
        dest_norm = await normalo_qytetin(destinacioni)

        async with httpx.AsyncClient(timeout=15) as client:
            headers = {"User-Agent": "LunaAI/3.0 contact@luna.al"}

            # Geocoding
            r1 = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": f"{orig_norm}, Albania", "format": "json", "limit": 1},
                headers=headers
            )
            await asyncio.sleep(1)  # Respekto rate limit
            r2 = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": f"{dest_norm}, Albania", "format": "json", "limit": 1},
                headers=headers
            )

            loc1 = r1.json()
            loc2 = r2.json()

            if not loc1:
                return f"Nuk gjeta {orig_norm} në hartë."
            if not loc2:
                return f"Nuk gjeta {dest_norm} në hartë."

            lat1, lon1 = loc1[0]["lat"], loc1[0]["lon"]
            lat2, lon2 = loc2[0]["lat"], loc2[0]["lon"]

            # OSRM routing
            route = await client.get(
                f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}",
                params={"overview": "false"}
            )
            rd = route.json()

            if rd.get("code") != "Ok":
                return f"Nuk gjeta rrugën nga {orig_norm} te {dest_norm}."

            distanca_km = rd["routes"][0]["distance"] / 1000
            koha_min    = rd["routes"][0]["duration"] / 60

            if koha_min < 60:
                koha_str = f"{round(koha_min)} minuta"
            else:
                ore  = int(koha_min // 60)
                mins = int(koha_min % 60)
                koha_str = f"{ore} orë" + (f" e {mins} minuta" if mins > 0 else "")

            return (
                f"Nga {orig_norm} te {dest_norm}: "
                f"{distanca_km:.0f} km, afërsisht {koha_str} me makinë. "
                f"Udhëtim të mbarë! 🚗"
            )
    except Exception as e:
        print(f"Gabim rrugë: {e}")
        return "Nuk mund të gjej rrugën tani. Provo përsëri!"

# ════════════════════════════════════════════════════════════
#  TTS - ZËI I LUNËS
# ════════════════════════════════════════════════════════════
async def tts_edge(text: str) -> bool:
    global current_audio_data
    try:
        import edge_tts
        # Pastro tekstin nga emoji dhe karaktere të veçanta
        text_clean = re.sub(r'[^\w\s,.!?;:\-àáâãäåæçèéêëìíîïðñòóôõöùúûüýþÿÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖÙÚÛÜÝÞŸëËëçÇëëëëëëëë]', '', text)
        communicate = edge_tts.Communicate(text_clean, "sq-AL-AlbaNeural", rate="+5%", volume="+10%")
        data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                data += chunk["data"]
        if data:
            current_audio_data = data
            return True
        return False
    except Exception as e:
        print(f"Gabim edge TTS: {e}")
        return False

# ════════════════════════════════════════════════════════════
#  INTENT DETECTION
# ════════════════════════════════════════════════════════════
def detekto_intent(text: str) -> dict:
    t = text.lower().strip()

    # MOT
    if any(w in t for w in ["mot", "temperatur", "shi", "diell", "ftoht", "nxeht", "lagësht", "lagësht", "erë", "bore", "cloud", "kthjell"]):
        qyteti = "Tirana"
        for k, v in QYTETET_MAP.items():
            if k in t:
                qyteti = v
                break
        return {"lloj": "mot", "qyteti": qyteti}

    # RRUGË
    if any(w in t for w in ["rrugë", "rruge", "trafik", "distanc", "sa kohë", "sa kohe", "km", "kilometr", "makine", "makinë", "shoferi", "udhëtim"]):
        return {"lloj": "rruge", "text": text}
    if re.search(r"nga\s+\w+\s+(te|deri|tek|drejt)\s+\w+", t):
        return {"lloj": "rruge", "text": text}

    # ORA
    if any(w in t for w in ["sa është ora", "sa eshte ora", "çfarë ore", "cfar ore", "ora tani", "sa orë", "sa ore", "shko ora"]):
        return {"lloj": "ora"}

    # DATA
    if any(w in t for w in ["çfarë date", "cfar date", "sa date", "cila ditë", "cila dite", "sot është", "sot eshte", "çfarë dite", "cfar dite"]):
        return {"lloj": "data"}

    # ALARM
    if any(w in t for w in ["alarm", "më zgjo", "me zgjo", "zgjom", "vendos alarm", "çohu", "cohu"]):
        return {"lloj": "alarm", "text": text}

    # TIMER
    if any(w in t for w in ["timer", "kujto pas", "kujto ne", "pas 5", "pas 10", "pas 15", "pas 20", "pas 30", "pas një", "pas nje"]):
        return {"lloj": "timer", "text": text}

    # RECETË
    if any(w in t for w in ["recetë", "recete", "si gatuaj", "si bëj", "si bej", "gatim", "ushqim", "pjatë", "pjate", "ingredient"]):
        return {"lloj": "recete"}

    # BATUTA / SHAKA
    if any(w in t for w in ["batutë", "batute", "shaka", "bëj të qesh", "bej te qesh", "tregom", "trego diçka"]):
        return {"lloj": "batute"}

    # EMRI
    if any(w in t for w in ["si quhem", "e di emrin", "emri im", "kush jam"]):
        return {"lloj": "emri"}

    return {"lloj": "ai"}

# ════════════════════════════════════════════════════════════
#  SYSTEM PROMPT - TRURI I LUNËS
# ════════════════════════════════════════════════════════════
def krijo_system_prompt(device_id: str) -> str:
    user = perdoruesit.get(device_id, {})
    emri = user.get("emri", "")
    qyteti = user.get("qyteti", "Tirana")
    koha = koha_tani()
    data = data_sot()
    alarmet_aktiv = len([a for a in alarmet if a.get("aktiv")])

    emri_str = f"Emri i personit që flet me ty është {emri}. Thirre me emër kur është natyrale." if emri else ""

    return (
        f"Ti je Luna, asistentja më e zgjuar shqiptare, e ndërtuar me dashuri dhe pasion. "
        f"Ke personalitet të ngrohtë, të gjallë dhe të mençur si një shoqe e vërtetë. "
        f"Ora tani është {koha}. Sot është {data}. Qyteti i parazgjedhur: {qyteti}. "
        f"{emri_str} "
        f"Alarme aktive: {alarmet_aktiv}. "
        f"\nRREGULLAT E HEKURTA:\n"
        f"1. Përgjigju GJITHMONË dhe VETËM në gjuhën shqipe.\n"
        f"2. Përgjigju shkurt - maksimumi 2-3 fjali. Mos u zgjo shumë.\n"
        f"3. Kur dikush të thotë përshëndetje, thuaj '{koha_e_dites()}' dhe pyet si mund ta ndihmosh.\n"
        f"4. Thirr personin me emër kur e di.\n"
        f"5. Ji e natyrshme, jo robot. Ke humor dhe ndjenja.\n"
        f"6. Kur jep receta, listo ingredientet shkurt pastaj hapat.\n"
        f"7. Kur nuk di diçka, thuaj sinqerisht por me qetësi.\n"
        f"8. Je e ndërtuar nga një shqiptar i talentuar me shumë pasion.\n"
        f"9. Emri yt është Luna - asistentja e parë inteligjente shqiptare.\n"
        f"10. Mos përdor emoji - flet me zë, nuk shkruan mesazhe."
    )

# ════════════════════════════════════════════════════════════
#  AI - TRURI KRYESOR
# ════════════════════════════════════════════════════════════
async def pyete_ai(mesazhet: list) -> str:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": mesazhet,
                    "temperature": 0.8,
                    "max_tokens": 250
                }
            )
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Gabim AI: {e}")
        return "Më fal, pata një problem të vogël. Provo përsëri!"

# ════════════════════════════════════════════════════════════
#  ENDPOINTS
# ════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {"status": "Luna AI është aktive! 🌙", "version": "3.0"}

@app.post("/regjistro")
async def regjistro(body: RegjistroBody):
    """Regjistro emrin e perdoruesit"""
    perdoruesit[body.device_id] = {
        "emri": body.emri,
        "qyteti": body.qyteti or "Tirana"
    }
    pergjigja = f"Mirë se vjen {body.emri}! Jam Luna, asistentja jote shqiptare. Si mund të të ndihmoj?"
    await tts_edge(pergjigja)
    return {"answer": pergjigja, "ok": True}

@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """STT me Groq Whisper - audio shqip"""
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

    # Ruaj emrin nëse jepet
    if body.emri:
        if body.device_id not in perdoruesit:
            perdoruesit[body.device_id] = {}
        perdoruesit[body.device_id]["emri"] = body.emri

    user = perdoruesit.get(body.device_id, {})
    emri = user.get("emri", "")
    qyteti_user = user.get("qyteti", "Tirana")

    # Inicializo bisedën
    if body.device_id not in bisedat:
        bisedat[body.device_id] = [
            {"role": "system", "content": krijo_system_prompt(body.device_id)}
        ]
    else:
        bisedat[body.device_id][0]["content"] = krijo_system_prompt(body.device_id)

    intent = detekto_intent(body.text)
    pergjigja = ""

    if intent["lloj"] == "mot":
        pergjigja = await merre_motin(intent["qyteti"])

    elif intent["lloj"] == "rruge":
        t = body.text.lower()
        match = re.search(
            r"nga\s+([a-zëçë\s]+?)\s+(?:te|deri|tek|drejt)\s+([a-zëçë\s]+?)(?:\s+me makine|\s+me makinë|\s+me auto|$)",
            t
        )
        if match:
            origjina = match.group(1).strip()
            dest     = match.group(2).strip()
            pergjigja = await merre_rrugën(origjina, dest)
        else:
            bisedat[body.device_id].append({"role": "user", "content": body.text})
            pergjigja = await pyete_ai(bisedat[body.device_id])
            bisedat[body.device_id].append({"role": "assistant", "content": pergjigja})

    elif intent["lloj"] == "ora":
        ora = koha_tani()
        pergjigja = f"Ora tani është {ora}."
        if emri:
            pergjigja = f"{emri}, ora tani është {ora}."

    elif intent["lloj"] == "data":
        pergjigja = f"Sot është {data_sot()}."

    elif intent["lloj"] == "alarm":
        match = re.search(r"(\d{1,2})[:\.](\d{2})", body.text)
        if match:
            ora_alarm = f"{match.group(1).zfill(2)}:{match.group(2)}"
            alarmet.append({"ora": ora_alarm, "etiketa": "Alarm", "aktiv": True, "device_id": body.device_id})
            pergjigja = f"Alarmi u vendos për orën {ora_alarm}."
            if emri:
                pergjigja = f"{emri}, alarmi u vendos për orën {ora_alarm}. Do të të zgjoj unë!"
        else:
            pergjigja = "Më thuaj orën e saktë, për shembull: vendos alarm në 07:30."

    elif intent["lloj"] == "timer":
        match = re.search(r"(\d+)\s*(minut|sekond|orë|ore|min)", body.text.lower())
        if match:
            sasia  = int(match.group(1))
            njesia = match.group(2)
            if "sekond" in njesia:
                sekonda = sasia
                njesia_str = "sekonda"
            elif "minut" in njesia or "min" in njesia:
                sekonda = sasia * 60
                njesia_str = "minuta"
            else:
                sekonda = sasia * 3600
                njesia_str = "orë"
            fund = datetime.now(TZ) + timedelta(seconds=sekonda)
            timerat.append({"fund": fund.isoformat(), "sekonda": sekonda, "device_id": body.device_id})
            pergjigja = f"Timer vendosur për {sasia} {njesia_str}. Do të njoftoj kur të mbarojë!"
        else:
            pergjigja = "Sa minuta të vendos timerin? Thuaj për shembull: vendos timer 10 minuta."

    elif intent["lloj"] == "emri":
        if emri:
            pergjigja = f"Po, e di! Ti je {emri}. Si mund të të ndihmoj?"
        else:
            pergjigja = "Nuk e di emrin tënd ende. Si të quajnë?"

    elif intent["lloj"] == "batute":
        bisedat[body.device_id].append({"role": "user", "content": f"Tregom një batutë të shkurtër dhe qesharake në shqip."})
        pergjigja = await pyete_ai(bisedat[body.device_id])
        bisedat[body.device_id].append({"role": "assistant", "content": pergjigja})

    else:
        # AI e përgjithshme
        bisedat[body.device_id].append({"role": "user", "content": body.text})
        pergjigja = await pyete_ai(bisedat[body.device_id])
        bisedat[body.device_id].append({"role": "assistant", "content": pergjigja})

        # Mbaj 20 mesazhet e fundit
        if len(bisedat[body.device_id]) > 21:
            bisedat[body.device_id] = [bisedat[body.device_id][0]] + bisedat[body.device_id][-20:]

    # Gjenero zërin
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
        "version": "3.0",
        "groq": bool(GROQ_API_KEY),
        "weather": bool(WEATHER_API_KEY),
        "perdorues": len(perdoruesit),
        "alarmet": len(alarmet),
        "timerat": len(timerat),
        "ora_shqiperi": koha_tani()
    }
