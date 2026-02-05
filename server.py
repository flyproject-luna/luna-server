import os
import re
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify

# OpenAI official Python SDK (Responses API)
from openai import OpenAI  #  [oai_citation:0‡OpenAI Platform](https://platform.openai.com/docs/guides/tools-code-interpreter?utm_source=chatgpt.com)

app = Flask(__name__)
client = OpenAI()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "")

# --- simple safety filter (keep it basic, no drama) ---
BAD_WORDS = {
    "kurv", "pidh", "kari", "qij", "mut", "byth", "peder", "nark", "droga",
    "vras", "ther", "bomb", "arm"
}

def clean_text(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

def redact_bad_words(s: str) -> str:
    out = s
    for w in BAD_WORDS:
        out = re.sub(rf"(?i)\b{re.escape(w)}\w*\b", "****", out)
    return out

def youtube_search_url(query: str) -> str:
    q = requests.utils.quote(query)
    return f"https://www.youtube.com/results?search_query={q}"

def openweather_geo(city: str):
    if not OPENWEATHER_API_KEY:
        return None
    url = "https://api.openweathermap.org/geo/1.0/direct"
    r = requests.get(url, params={"q": city, "limit": 1, "appid": OPENWEATHER_API_KEY}, timeout=12)
    if r.status_code != 200:
        return None
    data = r.json()
    if not data:
        return None
    return {"lat": data[0]["lat"], "lon": data[0]["lon"], "name": data[0].get("name", city), "country": data[0].get("country", "")}

def openweather_current(lat: float, lon: float):
    if not OPENWEATHER_API_KEY:
        return None
    url = "https://api.openweathermap.org/data/2.5/weather"
    r = requests.get(url, params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": "metric"}, timeout=12)
    if r.status_code != 200:
        return None
    return r.json()

def news_top():
    if not NEWS_API_KEY:
        return None
    url = "https://newsapi.org/v2/top-headlines"
    r = requests.get(url, params={"language": "en", "pageSize": 5, "apiKey": NEWS_API_KEY}, timeout=12)
    if r.status_code != 200:
        return None
    return r.json()

CITY_TZ = {
    "tirane": "Europe/Tirane",
    "tirana": "Europe/Tirane",
    "londer": "Europe/London",
    "london": "Europe/London",
    "new york": "America/New_York",
    "ny": "America/New_York",
    "rome": "Europe/Rome",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
}

def time_in_city(city: str):
    key = city.strip().lower()
    tz = CITY_TZ.get(key)
    if not tz:
        return None
    now = datetime.now(ZoneInfo(tz))
    return now.strftime("%H:%M")

def call_openai_general(q: str) -> str:
    # Keep it short + useful (ESP32 limits)
    system = (
        "You are Luna, a fast helpful assistant. "
        "Answer in Albanian, short, direct, no fluff. "
        "If user asks for links/actions, describe the action clearly."
    )
    resp = client.responses.create(  #  [oai_citation:1‡OpenAI Platform](https://platform.openai.com/docs/guides/tools-code-interpreter?utm_source=chatgpt.com)
        model=OPENAI_MODEL,
        instructions=system,
        input=q,
    )
    # safest extraction:
    text = ""
    for item in resp.output:
        if item.type == "message":
            for c in item.content:
                if c.type == "output_text":
                    text += c.text
    return clean_text(text)[:600]

@app.get("/")
def home():
    return "LUNA server running ✅  /ask?q=ora"

@app.get("/ask")
def ask():
    q = clean_text(request.args.get("q", ""))
    if not q:
        return jsonify(ok=False, error="Mungon parametri q. Shembull: /ask?q=ora"), 400

    q_low = q.lower()
    action = None

    # --- intents ---
    # YouTube: "luaj ..."
    if q_low.startswith("luaj "):
        song = q[5:].strip()
        if not song:
            return jsonify(ok=False, error="Shkruaj çfarë të luaj. p.sh: luaj happy nation"), 400
        url = youtube_search_url(song)
        answer = f"Ok. Kërkoje në YouTube: {song}"
        action = {"type": "open_url", "url": url}
        return jsonify(ok=True, answer=redact_bad_words(answer), action=action)

    # Weather: "moti ne ..." / "moti në ..."
    m = re.search(r"\bmoti\s+(ne|në)\s+(.+)$", q_low)
    if m:
        city = clean_text(m.group(2))
        geo = openweather_geo(city)
        if not geo:
            return jsonify(ok=False, error="S’po e gjej qytetin ose s’ke vendosur OPENWEATHER_API_KEY."), 400
        w = openweather_current(geo["lat"], geo["lon"])
        if not w:
            return jsonify(ok=False, error="S’po marr dot motin (kontrollo API key / limit)."), 400
        temp = w["main"]["temp"]
        feels = w["main"]["feels_like"]
        desc = w["weather"][0]["description"]
        answer = f"Moti në {geo['name']}: {temp:.0f}°C (ndihet {feels:.0f}°C), {desc}."
        return jsonify(ok=True, answer=redact_bad_words(answer), action=None)

    # Time: "ora" or "ora ne ..."
    if q_low == "ora":
        now = datetime.now(ZoneInfo("Europe/Tirane")).strftime("%H:%M")
        return jsonify(ok=True, answer=f"Ora tani: {now}.", action=None)

    m = re.search(r"\bora\s+(ne|në)\s+(.+)$", q_low)
    if m:
        city = clean_text(m.group(2))
        t = time_in_city(city)
        if not t:
            return jsonify(ok=False, error="S’e njoh këtë qytet për ora (shto në CITY_TZ)."), 400
        return jsonify(ok=True, answer=f"Ora në {city}: {t}.", action=None)

    # News: "lajmet" / "news"
    if "lajm" in q_low or "news" in q_low:
        data = news_top()
        if not data or "articles" not in data:
            return jsonify(ok=False, error="S’po marr lajmet (vendos NEWS_API_KEY)."), 400
        titles = [a["title"] for a in data["articles"][:5] if a.get("title")]
        answer = "Lajmet kryesore:\n- " + "\n- ".join(titles)
        return jsonify(ok=True, answer=redact_bad_words(answer)[:900], action=None)

    # Default: general AI answer
    ans = call_openai_general(q)
    ans = redact_bad_words(ans)
    return jsonify(ok=True, answer=ans, action=None)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=False)
