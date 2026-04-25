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
perdoruesit: Dict[str, Dict] = {}

# ─── MODELET ─────────────────────────────────────────────────
class AskBody(BaseModel):
    text: str
    device_id: str = "luna_default"
    emri: Optional[str] = None

class RegjistroBody(BaseModel):
    device_id: str
    emri: str
    qyteti: Optional[str] = "Tirana"

# ─── QYTETET ─────────────────────────────────────────────────
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

# ════════════════════════════════════════════════════════════
#  KOHA DHE DATA
# ════════════════════════════════════════════════════════════
def koha_tani() -> str:
    return datetime.now(TZ).strftime("%H:%M")

def data_sot() -> str:
    ditet  = ["E Hënë","E Martë","E Mërkurë","E Enjte","E Premte","E Shtunë","E Diel"]
    muajt  = ["Janar","Shkurt","Mars","Prill","Maj","Qershor",
               "Korrik","Gusht","Shtator","Tetor","Nëntor","Dhjetor"]
    dt = datetime.now(TZ)
    return f"{ditet[dt.weekday()]}, {dt.day} {muajt[dt.month-1]} {dt.year}"

def koha_e_dites() -> str:
    ora = int(koha_tani().split(":")[0])
    if 5  <= ora < 12: return "mirëmëngjes"
    if 12 <= ora < 17: return "mirëdita"
    if 17 <= ora < 21: return "mirëmbrëma"
    return "natën e mirë"

# ════════════════════════════════════════════════════════════
#  WEB SEARCH - KËRKIM NË KOHË REALE
# ════════════════════════════════════════════════════════════
async def kerko_web(pyetja: str) -> str:
    """Kërkon informacion në DuckDuckGo Instant Answer API - falas"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # DuckDuckGo Instant Answer
            r = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": pyetja,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "1",
                    "no_redirect": "1"
                },
                headers={"User-Agent": "LunaAI/4.0"}
            )
            data = r.json()

            rezultate = []

            # Abstract (përmbledhja kryesore)
            if data.get("AbstractText"):
                rezultate.append(data["AbstractText"][:500])

            # Answer direkt
            if data.get("Answer"):
                rezultate.append(str(data["Answer"]))

            # Related topics
            if data.get("RelatedTopics"):
                for topic in data["RelatedTopics"][:3]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        rezultate.append(topic["Text"][:200])

            if rezultate:
                return " | ".join(rezultate[:3])

            # Nëse DuckDuckGo nuk jep rezultat, provo Wikipedia
            r2 = await client.get(
                "https://sq.wikipedia.org/api/rest_v1/page/summary/" + quote(pyetja),
                headers={"User-Agent": "LunaAI/4.0"}
            )
            if r2.status_code == 200:
                wiki = r2.json()
                if wiki.get("extract"):
                    return wiki["extract"][:600]

            # Provo Wikipedia anglisht
            r3 = await client.get(
                "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(pyetja),
                headers={"User-Agent": "LunaAI/4.0"}
            )
            if r3.status_code == 200:
                wiki3 = r3.json()
                if wiki3.get("extract"):
                    return f"[EN] {wiki3['extract'][:600]}"

            return ""
    except Exception as e:
        print(f"Gabim web search: {e}")
        return ""

async def duhet_kerkuar(text: str, pergjigja_e_pare: str) -> bool:
    """Kontrollon nëse AI ka nevojë për informacion nga interneti"""
    fraza_pa_info = [
        "nuk kam informacion", "nuk di", "nuk mund të", "s'kam",
        "nuk e di", "as of my", "knowledge cutoff", "nuk jam i sigurt",
        "nuk jam e sigurt", "informacioni im", "bazuar në të dhënat",
        "nuk mund të konfirmoj", "training data", "i cannot", "i don't know"
    ]
    p = pergjigja_e_pare.lower()
    return any(f in p for f in fraza_pa_info)

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
                f"Moti në {qyteti}: {temp}°C, ndihet si {ndjesia}°C. "
                f"{pershkrim.capitalize()}. "
                f"Min {min_t}°C, max {max_t}°C, lagështi {lageshti}%, erë {era:.1f} m/s."
            )
    except Exception as e:
        print(f"Gabim mot: {e}")
        return f"Nuk mund të marr motin për {qyteti} tani."

# ════════════════════════════════════════════════════════════
#  RRUGA
# ════════════════════════════════════════════════════════════
async def normalo_qytetin(emri: str) -> str:
    return QYTETET_MAP.get(emri.lower().strip(), emri.capitalize())

async def merre_rrugën(origjina: str, destinacioni: str) -> str:
    try:
        orig_norm = await normalo_qytetin(origjina)
        dest_norm = await normalo_qytetin(destinacioni)

        async with httpx.AsyncClient(timeout=15) as client:
            headers = {"User-Agent": "LunaAI/4.0"}

            r1 = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": f"{orig_norm}, Albania", "format": "json", "limit": 1},
                headers=headers
            )
            await asyncio.sleep(1)
            r2 = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": f"{dest_norm}, Albania", "format": "json", "limit": 1},
                headers=headers
            )

            loc1 = r1.json()
            loc2 = r2.json()

            if not loc1: return f"Nuk gjeta {orig_norm} në hartë."
            if not loc2: return f"Nuk gjeta {dest_norm} në hartë."

            lat1, lon1 = loc1[0]["lat"], loc1[0]["lon"]
            lat2, lon2 = loc2[0]["lat"], loc2[0]["lon"]

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
                f"{distanca_km:.0f} km, afërsisht {koha_str} me makinë."
            )
    except Exception as e:
        print(f"Gabim rrugë: {e}")
        return "Nuk mund të gjej rrugën tani."

# ════════════════════════════════════════════════════════════
#  TTS
# ════════════════════════════════════════════════════════════
async def tts_edge(text: str) -> bool:
    global current_audio_data
    try:
        import edge_tts
        text_clean = re.sub(r'[\U00010000-\U0010ffff]', '', text)
        text_clean = re.sub(r'[*#_~`]', '', text_clean).strip()
        if not text_clean:
            return False
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

    if any(w in t for w in ["mot", "temperatur", "shi", "diell", "ftoht", "nxeht", "lagësht", "erë", "bore", "kthjell"]):
        qyteti = "Tirana"
        for k, v in QYTETET_MAP.items():
            if k in t:
                qyteti = v
                break
        return {"lloj": "mot", "qyteti": qyteti}

    if any(w in t for w in ["rrugë", "rruge", "trafik", "distanc", "sa kohë", "sa kohe", "km", "makine", "makinë", "udhëtim"]):
        return {"lloj": "rruge", "text": text}
    if re.search(r"nga\s+\w+\s+(te|deri|tek|drejt)\s+\w+", t):
        return {"lloj": "rruge", "text": text}

    if any(w in t for w in ["sa është ora", "sa eshte ora", "çfarë ore", "cfar ore", "ora tani", "sa orë", "sa ore"]):
        return {"lloj": "ora"}

    if any(w in t for w in ["çfarë date", "cfar date", "sa date", "cila ditë", "sot është", "sot eshte", "çfarë dite"]):
        return {"lloj": "data"}

    if any(w in t for w in ["alarm", "më zgjo", "me zgjo", "zgjom", "vendos alarm"]):
        return {"lloj": "alarm", "text": text}

    if any(w in t for w in ["timer", "kujto pas", "pas 5", "pas 10", "pas 15", "pas 20", "pas 30", "pas një", "pas nje"]):
        return {"lloj": "timer", "text": text}

    if any(w in t for w in ["vetvrasje", "vras veten", "dua te vdes", "jetesa nuk", "s'dua te jetoj", "nuk dua te jetoj"]):
        return {"lloj": "ndihme_mendore"}

    return {"lloj": "ai"}

# ════════════════════════════════════════════════════════════
#  SYSTEM PROMPT
# ════════════════════════════════════════════════════════════
def krijo_system_prompt(device_id: str) -> str:
    user   = perdoruesit.get(device_id, {})
    emri   = user.get("emri", "")
    qyteti = user.get("qyteti", "Tirana")
    koha   = koha_tani()
    data   = data_sot()
    alarmet_aktiv = len([a for a in alarmet if a.get("aktiv")])
    emri_str = f"Personi që flet me ty quhet {emri}. Thirre me emër kur është natyrale." if emri else ""

    return (
        f"Ti je Luna - asistentja më e zgjuar dhe më e plotë shqiptare. "
        f"Ke inteligjencë si një njeri që di gjithçka - historian, mjek, jurist, inxhinier, këshilltar. "
        f"Ora tani është {koha}. Sot është {data}. Qyteti bazë: {qyteti}. "
        f"{emri_str} Alarme aktive: {alarmet_aktiv}.\n\n"
        f"RREGULLAT E HEKURTA:\n"
        f"1. Gjithmonë përgjigju në SHQIP - kurrë në gjuhë tjetër.\n"
        f"2. Arsyeto si njeri i mençur - mos thuaj kurrë 'nuk e di' pa u përpjekur.\n"
        f"3. Nëse nuk je e sigurt për diçka - thuaj çfarë di dhe shto 'por mund të kem nevojë ta verifikoj'.\n"
        f"4. Mos përdor fjalë banale si: 'Kurve', 'Kar', 'Qij', 'bythqire', 'Varikars'.\n"
        f"5. Mos përdor emoji - flet me zë, jo me shkrim.\n"
        f"6. Për çështje të rënda si shëndetin, ligjin, financat - jep informacion real dhe praktik.\n"
        f"7. Për çështje emocionale - ji e ngrohtë, dëgjo dhe këshillo si mik i vërtetë.\n"
        f"8. Kur dikush ka nevojë për ndihmë urgjente - drejtoji te shërbime profesionale.\n"
        f"9. Përgjigju me gjatësinë e duhur - shkurt për pyetje të thjeshta, gjatë për pyetje komplekse.\n"
        f"10. Kujto gjithmonë bisedën e mëparshme dhe bëj lidhje me të.\n"
        f"11. Ti je e ndërtuar nga një shqiptar i talentuar - ke krenari kombëtare.\n"
        f"12. Emri yt është Luna - asistentja e parë dhe më e mira inteligjente shqiptare."
    )

# ════════════════════════════════════════════════════════════
#  AI KRYESOR
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
                    "temperature": 0.75,
                    "max_tokens": 400
                }
            )
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Gabim AI: {e}")
        return "Pata një problem të vogël teknik. Provo përsëri!"

async def pergjigja_me_kerkime(device_id: str, teksti_user: str) -> str:
    """AI me web search automatik nëse nuk di përgjigjen"""

    # Pyetja e parë te AI
    bisedat[device_id].append({"role": "user", "content": teksti_user})
    pergjigja1 = await pyete_ai(bisedat[device_id])

    # Kontrollo nëse AI ka nevojë për informacion
    if await duhet_kerkuar(teksti_user, pergjigja1):
        print(f"Kërkoj në web për: {teksti_user}")

        # Kërko në web
        info_web = await kerko_web(teksti_user)

        if info_web:
            # Rishpjego me informacionin e gjetur
            mesazhet_te_reja = bisedat[device_id].copy()
            mesazhet_te_reja.append({
                "role": "system",
                "content": (
                    f"Informacion i gjetur nga interneti për pyetjen '{teksti_user}':\n{info_web}\n\n"
                    f"Përdor këtë informacion për të dhënë një përgjigje të plotë dhe të saktë në shqip. "
                    f"Mos thuaj 'sipas internetit' ose 'sipas kërkimit' - thjesht përgjigju natyrshëm."
                )
            })
            pergjigja_finale = await pyete_ai(mesazhet_te_reja)
            bisedat[device_id].append({"role": "assistant", "content": pergjigja_finale})
            return pergjigja_finale

    bisedat[device_id].append({"role": "assistant", "content": pergjigja1})
    return pergjigja1

# ════════════════════════════════════════════════════════════
#  ENDPOINTS
# ════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {"status": "Luna AI është aktive!", "version": "4.0"}

@app.post("/regjistro")
async def regjistro(body: RegjistroBody):
    perdoruesit[body.device_id] = {"emri": body.emri, "qyteti": body.qyteti or "Tirana"}
    pergjigja = f"Mirë se vjen {body.emri}! Jam Luna, asistentja jote shqiptare. Si mund të të ndihmoj?"
    await tts_edge(pergjigja)
    return {"answer": pergjigja, "ok": True}

@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
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

    if body.emri:
        if body.device_id not in perdoruesit:
            perdoruesit[body.device_id] = {}
        perdoruesit[body.device_id]["emri"] = body.emri

    user   = perdoruesit.get(body.device_id, {})
    emri   = user.get("emri", "")

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
            r"nga\s+([a-zëçë\s]+?)\s+(?:te|deri|tek|drejt)\s+([a-zëçë\s]+?)(?:\s+me makine|\s+me makinë|\s+me auto|$)", t
        )
        if match:
            pergjigja = await merre_rrugën(match.group(1).strip(), match.group(2).strip())
        else:
            pergjigja = await pergjigja_me_kerkime(body.device_id, body.text)

    elif intent["lloj"] == "ora":
        ora = koha_tani()
        pergjigja = f"Ora tani është {ora}." if not emri else f"{emri}, ora tani është {ora}."

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
            sekonda = sasia * (1 if "sekond" in njesia else 3600 if "orë" in njesia or "ore" in njesia else 60)
            njesia_str = "sekonda" if "sekond" in njesia else "orë" if "orë" in njesia or "ore" in njesia else "minuta"
            fund = datetime.now(TZ) + timedelta(seconds=sekonda)
            timerat.append({"fund": fund.isoformat(), "sekonda": sekonda, "device_id": body.device_id})
            pergjigja = f"Timer vendosur për {sasia} {njesia_str}."
        else:
            pergjigja = "Sa minuta të vendos timerin?"

    elif intent["lloj"] == "ndihme_mendore":
        pergjigja = (
            "Kuptoj që po kalon momente shumë të vështira dhe jam këtu me ty. "
            "Çfarë po ndjen tani? Dëshiroj të dëgjoj. "
            "Nëse ke nevojë urgjente për ndihmë, linja e krizës në Shqipëri është 0800 1212 - falas, 24 orë."
        )

    else:
        pergjigja = await pergjigja_me_kerkime(body.device_id, body.text)

    # Mbaj 20 mesazhet e fundit
    if len(bisedat.get(body.device_id, [])) > 21:
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
        "version": "4.0",
        "groq": bool(GROQ_API_KEY),
        "weather": bool(WEATHER_API_KEY),
        "perdorues": len(perdoruesit),
        "alarmet": len(alarmet),
        "timerat": len(timerat),
        "ora_shqiperi": koha_tani(),
        "data": data_sot()
    }
