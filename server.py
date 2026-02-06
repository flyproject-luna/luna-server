import os
import re
import requests
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from datetime import datetime
from zoneinfo import ZoneInfo

APP_TZ = os.getenv("APP_TZ", "Europe/Tirane")
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "Tirana")

OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY", "")  # opsional, por duhet për motin
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_KEY", "")  # opsional (trafik/distanca)

app = FastAPI(title="ESP32 Voice Backend", version="1.0")


# -----------------------
# Helpers
# -----------------------
def now_local():
    dt = datetime.now(ZoneInfo(APP_TZ))
    return dt

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()

def mediawiki_summary(topic: str, lang: str = "sq") -> str:
    """
    Merr hyrjen (intro) pa HTML nga Wikipedia në gjuhën që zgjedh.
    lang: "sq" ose "en" etj.
    """
    topic = topic.strip().replace(" ", "_")
    endpoint = f"https://{lang}.wikipedia.org/w/api.php"

    params = {
        "action": "query",
        "prop": "extracts",
        "exintro": "1",
        "explaintext": "1",
        "redirects": "1",
        "titles": topic,
        "format": "json",
    }

    r = requests.get(endpoint, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()

    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return "S’po gjej asgjë në Wikipedia."

    page = next(iter(pages.values()))
    if "missing" in page:
        return "S’po e gjej atë temë në Wikipedia."

    extract = (page.get("extract") or "").strip()
    title = page.get("title", topic.replace("_", " "))

    if not extract:
        return f"Gjeta faqen “{title}”, por s’ka përmbajtje të lexueshme."
    # Shkurto pak që të mos dalë roman:
    if len(extract) > 700:
        extract = extract[:700].rsplit(".", 1)[0] + "."
    return f"{title}: {extract}"

def openweather_current(city: str) -> str:
    if not OPENWEATHER_KEY:
        return "S’kam OPENWEATHER_KEY. Vendose në env dhe je ok."
    endpoint = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": OPENWEATHER_KEY,
        "units": "metric",
        "lang": "sq",
    }
    r = requests.get(endpoint, params=params, timeout=10)
    if r.status_code != 200:
        return f"S’po marr dot motin për {city}."
    data = r.json()
    temp = data["main"]["temp"]
    feels = data["main"]["feels_like"]
    desc = data["weather"][0]["description"]
    return f"Në {city}: {desc}, {temp:.0f}°C (ndjehet si {feels:.0f}°C)."

def traffic_eta(origin: str, destination: str) -> str:
    """
    Opsionale: kërkon Google Maps Directions API.
    """
    if not GOOGLE_MAPS_KEY:
        return "S’kam GOOGLE_MAPS_KEY (trafiku është opsional)."
    endpoint = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin,
        "destination": destination,
        "departure_time": "now",
        "key": GOOGLE_MAPS_KEY,
    }
    r = requests.get(endpoint, params=params, timeout=10)
    if r.status_code != 200:
        return "S’po marr dot trafikun."
    data = r.json()
    routes = data.get("routes", [])
    if not routes:
        return "S’po gjej rrugë për atë destinacion."
    leg = routes[0]["legs"][0]
    dur = leg.get("duration_in_traffic", leg.get("duration", {})).get("text", "")
    dist = leg.get("distance", {}).get("text", "")
    return f"Me trafik: {dur}, distanca: {dist}."

def youtube_link(query: str) -> str:
    """
    Pa API key: thjesht link kërkimi YouTube (praktike për telefon/TV).
    """
    q = requests.utils.quote(query.strip())
    return f"Hape këtë në YouTube: https://www.youtube.com/results?search_query={q}"


# -----------------------
# Simple router (intents pa AI)
# -----------------------
def route(text: str) -> str:
    t = normalize(text)

    # Ora / data
    if any(k in t for k in ["sa është ora", "sa eshte ora", "ora sa", "time"]):
        dt = now_local()
        return f"Ora është {dt.strftime('%H:%M')}."
    if any(k in t for k in ["çfarë date", "cfare date", "data sot", "date"]):
        dt = now_local()
        return f"Sot është {dt.strftime('%d.%m.%Y')}."

    # Moti
    if "moti" in t or "weather" in t:
        # nxjerr qytetin nëse e përmend: "moti ne durres"
        m = re.search(r"(?:n[eë]\s+)([a-zçë\s]+)$", t)
        city = DEFAULT_CITY
        if m:
            city = m.group(1).strip().title()
        return openweather_current(city)

    # Wikipedia / MediaWiki
    # shembuj: "wiki Skënderbeu", "wikipedia Albert Einstein", "kush eshte ...", "cfare eshte ..."
    if t.startswith("wiki ") or t.startswith("wikipedia "):
        topic = text.split(" ", 1)[1].strip()
        return mediawiki_summary(topic, lang="sq")
    if t.startswith("who is ") or t.startswith("what is "):
        topic = text.split(" ", 2)[2].strip() if len(text.split(" ", 2)) == 3 else text
        return mediawiki_summary(topic, lang="en")
    if t.startswith("kush eshte ") or t.startswith("kush është "):
        topic = text.split(" ", 2)[2].strip() if len(text.split(" ", 2)) == 3 else text
        return mediawiki_summary(topic, lang="sq")
    if t.startswith("cfare eshte ") or t.startswith("çfare eshte ") or t.startswith("çfarë është "):
        topic = text.split(" ", 2)[2].strip() if len(text.split(" ", 2)) == 3 else text
        return mediawiki_summary(topic, lang="sq")

    # Trafik (opsional)
    # format: "trafik nga Tirana te Durres"
    if t.startswith("trafik"):
        m = re.search(r"nga\s+(.+?)\s+te\s+(.+)$", t)
        if not m:
            return "Shkruaje: trafik nga <origjina> te <destinacioni>."
        origin = m.group(1).strip().title()
        dest = m.group(2).strip().title()
        return traffic_eta(origin, dest)

    # YouTube
    # format: "luaj youtube emri i kenges"
    if "youtube" in t or t.startswith("luaj "):
        q = re.sub(r"^(luaj\s+)?(youtube\s+)?", "", text, flags=re.I).strip()
        if not q:
            return "Më thuaj çfarë të kërkoj në YouTube."
        return youtube_link(q)

    return "S’e kapa. Provo: 'moti ne Tirane', 'wiki Skenderbeu', 'sa eshte ora', 'trafik nga Tirana te Durres', 'youtube ...'."


# -----------------------
# API endpoint
# -----------------------
@app.get("/ask")
def ask(text: str = Query(..., min_length=1)):
    answer = route(text)
    return JSONResponse({"ok": True, "text": text, "answer": answer})
