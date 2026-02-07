import os
import re
import math
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "").strip()

MODEL = os.getenv("LUNA_MODEL", "openai/gpt-4o-mini").strip()
DEFAULT_CITY = os.getenv("LUNA_DEFAULT_CITY", "Tirana").strip()
DEFAULT_TZ = os.getenv("LUNA_DEFAULT_TZ", "Europe/Tirane").strip()

app = FastAPI()

class AskBody(BaseModel):
    text: str
    profile: dict | None = None   # {name, city, tz, style, family, daily}

# -------------------- Basics --------------------
@app.get("/", response_class=PlainTextResponse)
def root():
    return "ok"

@app.get("/health")
def health():
    return {"ok": True}

# -------------------- Time --------------------
CITY_TZ = {
    "tirana": "Europe/Tirane",
    "tiranë": "Europe/Tirane",
    "tirane": "Europe/Tirane",
    "london": "Europe/London",
    "londer": "Europe/London",
    "rome": "Europe/Rome",
    "roma": "Europe/Rome",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "new york": "America/New_York",
    "nyc": "America/New_York",
}

MONTHS_SQ = ["janar","shkurt","mars","prill","maj","qershor","korrik","gusht","shtator","tetor","nëntor","dhjetor"]

def fmt_sq(dt: datetime) -> str:
    return f"{dt.hour:02d}:{dt.minute:02d}, {dt.day:02d} {MONTHS_SQ[dt.month-1]} {dt.year}"

def safe_tz(tz: str | None) -> str:
    tz = (tz or "").strip()
    if not tz:
        return DEFAULT_TZ
    try:
        ZoneInfo(tz)
        return tz
    except Exception:
        return DEFAULT_TZ

def time_for_city(city: str, fallback_tz: str) -> tuple[str,str]:
    c = (city or "").strip().lower()
    tz = CITY_TZ.get(c, fallback_tz)
    dt = datetime.now(ZoneInfo(tz))
    return tz, fmt_sq(dt)

def extract_time_city(text: str) -> str | None:
    t = text.lower().strip()
    # "sa eshte ora ne london" / "ora ne london"
    m = re.search(r"(?:sa\s*(?:eshte|është)\s*ora\s*(?:ne|në)\s*)([a-zçë\s\-]+)", t)
    if m:
        return m.group(1).strip()
    m = re.search(r"(?:ora\s*(?:ne|në)\s*)([a-zçë\s\-]+)$", t)
    if m:
        return m.group(1).strip()
    return None

def is_time_q(text: str) -> bool:
    t = text.lower()
    return ("ora" in t) and ("sa" in t or "cila" in t or "ne " in t or "në " in t)

# -------------------- Math --------------------
_ALLOWED = set("0123456789+-*/().,% ")
def extract_expr(text: str) -> str | None:
    t = text.lower()
    t = t.replace("sa bejne", "").replace("sa bëjnë", "").replace("sa eshte", "").replace("sa është", "")
    # kap një fragment matematikor
    m = re.findall(r"[0-9\.\,\+\-\*\/\(\)\%\s]{3,}", t)
    if not m:
        return None
    expr = max(m, key=len).strip().replace(",", ".").replace(" ", "")
    if not expr:
        return None
    if any(ch not in _ALLOWED for ch in expr):
        return None
    if re.search(r"[A-Za-z_]", expr):
        return None
    return expr

def eval_math(expr: str) -> float:
    if not expr or len(expr) > 64:
        raise ValueError("bad expr")
    val = eval(expr, {"__builtins__": None}, {})
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        raise ValueError("bad result")
    if math.isinf(val) or math.isnan(val):
        raise ValueError("bad result")
    return float(val)

def is_math_q(text: str) -> bool:
    t = text.lower()
    if "sa bejne" in t or "sa bëjnë" in t or "sa eshte" in t or "sa është" in t:
        return extract_expr(text) is not None
    return bool(re.search(r"\d\s*[\+\-\*\/]\s*\d", t))

# -------------------- Fixed Knowledge (exact) --------------------
def is_name_q(text: str) -> bool:
    t = text.lower()
    return "si e ke emrin" in t or "si quhesh" in t or "emri yt" in t

def formula_answer(text: str) -> str | None:
    t = text.lower()
    if "dallor" in t or "dallimi i katror" in t or "a²-b²" in t or "a2-b2" in t:
        return "Formula e dallimit të katrorëve: a² − b² = (a − b)(a + b)."
    if "fotosintez" in t:
        return "Fotosinteza: 6CO₂ + 6H₂O + dritë → C₆H₁₂O₆ + 6O₂."
    return None

def is_formula_q(text: str) -> bool:
    t = text.lower()
    return ("formul" in t) or ("fotosintez" in t) or ("dallor" in t)

# -------------------- Weather --------------------
def get_weather(city: str):
    if not OPENWEATHER_API_KEY:
        return None
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric", "lang": "sq"}
    r = requests.get(url, params=params, timeout=15)
    if r.status_code != 200:
        return None
    data = r.json()
    temp = data["main"]["temp"]
    hum = data["main"]["humidity"]
    wind = data["wind"]["speed"]
    desc = data["weather"][0]["description"]
    return f"Moti në {city}: {temp:.1f}°C, {desc}. Lagështia {hum}%, era {wind:.2f} m/s."

def is_weather_q(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in ["moti", "temperatura", "sa grad", "parashikimi", "weather"])

@app.get("/weather")
def weather(city: str = DEFAULT_CITY):
    w = get_weather(city)
    if not w:
        raise HTTPException(status_code=400, detail="Weather not available")
    return {"ok": True, "answer": w}

# -------------------- Traffic (TomTom) --------------------
# TomTom gives traffic-aware routing time when you request route with traffic enabled.
# Needs TOMTOM_API_KEY. Pricing/free allowance varies; see TomTom pricing/allowance docs.  [oai_citation:1‡developer.tomtom.com](https://developer.tomtom.com/pricing?utm_source=chatgpt.com)

def tomtom_geocode(query: str) -> tuple[float,float] | None:
    if not TOMTOM_API_KEY:
        return None
    url = "https://api.tomtom.com/search/2/geocode/" + requests.utils.quote(query) + ".json"
    params = {"key": TOMTOM_API_KEY, "limit": 1}
    r = requests.get(url, params=params, timeout=20)
    if r.status_code != 200:
        return None
    data = r.json()
    if not data.get("results"):
        return None
    pos = data["results"][0]["position"]
    return float(pos["lat"]), float(pos["lon"])

def tomtom_route_with_traffic(from_lat: float, from_lon: float, to_lat: float, to_lon: float):
    if not TOMTOM_API_KEY:
        return None
    url = f"https://api.tomtom.com/routing/1/calculateRoute/{from_lat},{from_lon}:{to_lat},{to_lon}/json"
    params = {
        "key": TOMTOM_API_KEY,
        "traffic": "true",
        "travelMode": "car",
        "routeType": "fastest",
        "computeTravelTimeFor": "all",
        "sectionType": "traffic",
    }
    r = requests.get(url, params=params, timeout=25)
    if r.status_code != 200:
        return None
    data = r.json()
    routes = data.get("routes") or []
    if not routes:
        return None
    summary = routes[0].get("summary") or {}
    travel_seconds = int(summary.get("travelTimeInSeconds") or 0)
    traffic_delay = int(summary.get("trafficDelayInSeconds") or 0)
    length_m = int(summary.get("lengthInMeters") or 0)
    return travel_seconds, traffic_delay, length_m

def sec_to_hm(sec: int) -> str:
    if sec <= 0:
        return "0 min"
    m = sec // 60
    h = m // 60
    m2 = m % 60
    return f"{h}h {m2}m" if h else f"{m2} min"

@app.get("/traffic")
def traffic(from_q: str, to_q: str):
    # from_q / to_q = address/place (e.g. "21 Dhjetori, Tirana" -> "TEG, Tirana")
    if not TOMTOM_API_KEY:
        raise HTTPException(status_code=500, detail="TOMTOM_API_KEY missing")

    a = tomtom_geocode(from_q)
    b = tomtom_geocode(to_q)
    if not a or not b:
        raise HTTPException(status_code=400, detail="Could not geocode from/to")

    route = tomtom_route_with_traffic(a[0], a[1], b[0], b[1])
    if not route:
        raise HTTPException(status_code=502, detail="TomTom routing failed")

    travel_seconds, traffic_delay, length_m = route
    km = length_m / 1000.0

    answer = (
        f"Trafiku (live): {from_q} → {to_q}\n"
        f"Koha: {sec_to_hm(travel_seconds)} (vonesë nga trafiku: {sec_to_hm(traffic_delay)}), "
        f"distanca: {km:.1f} km."
    )
    return {"ok": True, "answer": answer}

def is_traffic_q(text: str) -> bool:
    t = text.lower()
    return "trafik" in t or "traffic" in t

def extract_route(text: str) -> tuple[str,str] | None:
    # “trafiku nga X deri te Y”
    t = text.strip()
    low = t.lower()
    m = re.search(r"nga\s+(.*?)\s+(deri\s+te|deri\s+tek|te|tek)\s+(.*)$", low)
    if not m:
        return None
    # përdor substrings nga origjinali për të ruajtur shkronjat
    # thjesht marrim nga low indices:
    start = low.find("nga ") + 4
    mid = low.find(m.group(2))
    from_part = t[start:mid].strip(" ?!.")
    to_part = t[mid + len(m.group(2)):].strip(" ?!.")
    return from_part, to_part

# -------------------- LLM --------------------
def ask_llm(user_text: str, context: dict) -> str:
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY missing")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    system = (
        "Je Luna, asistente AI në shqip për smart clock.\n"
        "Rregulla të forta:\n"
        "- MOS shpik kurrë orë/datë/moti/trafik.\n"
        "- Për gjëra faktike përdor vetëm CONTEXT.\n"
        "- Përgjigju sipas stilit: shkurt/normal/gjate.\n"
        "- Nëse mungon info, bëj 1 pyetje të shpejtë.\n"
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "system", "content": "CONTEXT_JSON:\n" + json.dumps(context, ensure_ascii=False)},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.4,
        "max_tokens": 320,
    }

    r = requests.post(url, headers=headers, json=payload, timeout=45)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OpenRouter error: {r.text}")

    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

# -------------------- ASK (router) --------------------
@app.post("/ask")
def ask(body: AskBody):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    profile = body.profile or {}
    user_city = (profile.get("city") or DEFAULT_CITY).strip()
    user_tz = safe_tz(profile.get("tz"))

    # 1) identity (fixed)
    if is_name_q(text):
        return {"ok": True, "answer": "Unë jam Luna."}

    # 2) formulas (exact)
    if is_formula_q(text):
        ans = formula_answer(text)
        if ans:
            return {"ok": True, "answer": ans}

    # 3) time (exact) — city aware
    if is_time_q(text):
        city = extract_time_city(text) or user_city
        tz, tstr = time_for_city(city, user_tz)
        return {"ok": True, "answer": f"Ora tani në {city.title()} është {tstr}."}

    # 4) math (exact)
    if is_math_q(text):
        expr = extract_expr(text)
        if not expr:
            return {"ok": True, "answer": "Ma shkruaj shprehjen tamam (p.sh. 28*17)."}
        try:
            val = eval_math(expr)
        except Exception:
            return {"ok": True, "answer": "S’e llogarita dot. Shkruaje më thjesht (p.sh. 28*17)."}
        if abs(val - round(val)) < 1e-12:
            return {"ok": True, "answer": str(int(round(val)))}
        return {"ok": True, "answer": str(val)}

    # 5) weather (exact)
    if is_weather_q(text):
        w = get_weather(user_city)
        if not w:
            return {"ok": True, "answer": "S’po marr dot motin tani."}
        return {"ok": True, "answer": w}

    # 6) traffic (live) — TomTom
    if is_traffic_q(text):
        route = extract_route(text)
        if not route:
            return {"ok": True, "answer": "Ma jep kështu: 'trafiku nga [nisja] deri te [destinacioni]'."}
        if not TOMTOM_API_KEY:
            return {"ok": True, "answer": "S’ka TOMTOM_API_KEY në server."}
        from_q, to_q = route
        # ndihmë: nëse s’ka qytet në tekst, shto Tirana
        if "," not in from_q:
            from_q = f"{from_q}, {user_city}"
        if "," not in to_q:
            to_q = f"{to_q}, {user_city}"

        a = tomtom_geocode(from_q)
        b = tomtom_geocode(to_q)
        if not a or not b:
            return {"ok": True, "answer": "S’i gjeta pikat. Shkruaji më qartë (me lagje/rrugë)."}
        route_data = tomtom_route_with_traffic(a[0], a[1], b[0], b[1])
        if not route_data:
            return {"ok": True, "answer": "Trafiku s’po del tani. Provo prap."}
        travel_seconds, traffic_delay, length_m = route_data
        km = length_m / 1000.0
        return {"ok": True, "answer": f"Trafiku (live): {from_q} → {to_q}. Koha {sec_to_hm(travel_seconds)} (vonesë {sec_to_hm(traffic_delay)}), {km:.1f} km."}

    # 7) general AI — with memory context (no hallucination allowed)
    dt = datetime.now(ZoneInfo(user_tz))
    context = {
        "now_local": fmt_sq(dt),
        "tz": user_tz,
        "user_city": user_city,
        "style": profile.get("style", "shkurt"),
        "user_name": profile.get("name", ""),
        "family": profile.get("family", []),
        "daily_notes": profile.get("daily", []),
        "rule": "Do NOT invent time/date/weather/traffic. Use tools or context."
    }

    answer = ask_llm(text, context)
    return {"ok": True, "answer": answer}




if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
