import os
import re
import math
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()

DEFAULT_CITY = os.getenv("DEFAULT_CITY", "Tirana").strip()
TZ_NAME = os.getenv("TZ_NAME", "Europe/Tirane").strip()

app = FastAPI()


class AskBody(BaseModel):
    text: str
    city: str | None = None


@app.get("/")
def root():
    return "ok"


@app.get("/health")
def health():
    return {"ok": True}


# ---------- Helpers: time/date ----------
def now_local():
    try:
        return datetime.now(ZoneInfo(TZ_NAME))
    except Exception:
        return datetime.now(ZoneInfo("Europe/Tirane"))


def format_datetime_sq(dt: datetime) -> str:
    # Minimal, pa libra ekstra
    months = [
        "janar", "shkurt", "mars", "prill", "maj", "qershor",
        "korrik", "gusht", "shtator", "tetor", "nëntor", "dhjetor"
    ]
    month = months[dt.month - 1]
    return f"{dt.hour:02d}:{dt.minute:02d}, {dt.day:02d} {month} {dt.year}"


def is_time_question(t: str) -> bool:
    t = t.lower()
    keys = [
        "sa eshte ora", "sa është ora", "ora sa", "cila ore", "cila është ora",
        "sa është data", "sa eshte data", "cila date", "cila është data",
        "sot cfare date", "sot çfarë date", "sot çfare date", "today"
    ]
    return any(k in t for k in keys)


# ---------- Helpers: math ----------
_allowed_math = re.compile(r"^[0-9\.\,\+\-\*\/\(\)\s]+$")

def extract_math_expr(text: str) -> str | None:
    t = text.lower().strip()
    # kap formatet tipike: "sa bejne 28*17", "28 * 17", "sa është 10/2"
    t = t.replace("sa bejne", "").replace("sa bëjnë", "").replace("sa eshte", "").replace("sa është", "")
    t = t.replace("=", " ")
    t = t.strip()

    # gjej një fragment që duket si shprehje
    m = re.findall(r"[0-9\.\,\+\-\*\/\(\)\s]{3,}", t)
    if not m:
        return None
    expr = max(m, key=len).strip()

    # normalizo presjen në pikë
    expr = expr.replace(",", ".")

    if not _allowed_math.match(expr):
        return None
    return expr


def safe_eval_math(expr: str) -> float:
    # eval i kontrolluar: vetëm numra + operatorë
    # pa funksione, pa emra, pa __
    try:
        val = eval(expr, {"__builtins__": None}, {})
    except Exception as e:
        raise ValueError(str(e))
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        raise ValueError("Invalid expression")
    if math.isinf(val) or math.isnan(val):
        raise ValueError("Invalid result")
    return float(val)


def is_math_question(text: str) -> bool:
    t = text.lower()
    if "sa bejne" in t or "sa bëjnë" in t or "sa eshte" in t or "sa është" in t:
        return extract_math_expr(text) is not None
    # edhe nëse përdor direkt operatorë
    return bool(re.search(r"\d\s*[\+\-\*\/]\s*\d", t))


# ---------- Weather ----------
def get_weather(city: str):
    if not OPENWEATHER_API_KEY:
        return None

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "sq",
    }
    r = requests.get(url, params=params, timeout=15)
    if r.status_code != 200:
        return None

    data = r.json()
    temp = data["main"]["temp"]
    hum = data["main"]["humidity"]
    wind = data["wind"]["speed"]
    desc = data["weather"][0]["description"]
    return f"Moti në {city}: {temp:.1f}°C, {desc}. Lagështia {hum}%, era {wind:.2f} m/s."


def is_weather_question(text: str) -> bool:
    t = text.lower()
    keys = ["moti", "parashikimi", "temperature", "temperatura", "shi", "era", "lagështia", "humidity", "weather"]
    return any(k in t for k in keys)


# ---------- Traffic (placeholder) ----------
def is_traffic_question(text: str) -> bool:
    t = text.lower()
    keys = ["trafik", "traffic", "sa do", "sa duhet", "sa minuta", "sa kohe", "sa kohë", "rruga", "route"]
    return any(k in t for k in keys) and ("trafik" in t or "traffic" in t or "rrug" in t)


# ---------- LLM ----------
def ask_llm(prompt: str):
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY missing")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        # këto ndihmojnë te OpenRouter logs / rate-limits, s’janë të detyrueshme
        "HTTP-Referer": os.getenv("APP_URL", "http://localhost"),
        "X-Title": "Luna Server",
    }

    system = (
        "Je Luna, asistente AI në shqip. "
        "Jep përgjigje të shkurtra, të sakta, pa shumë llafe. "
        "Kurrë mos shpik orë/datë apo trafik live. "
        "Nëse s’ke të dhëna për trafik, kërko start+destinacion dhe orën e nisjes. "
        "Për receta: jep përbërës + hapa. "
        "Për pyetje shkollore: jep përgjigje të qartë."
    )

    payload = {
        "model": os.getenv("LLM_MODEL", "openai/gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 350,
    }

    r = requests.post(url, headers=headers, json=payload, timeout=45)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OpenRouter error: {r.text}")

    data = r.json()
    return data["choices"][0]["message"]["content"].strip()


# ---------- Main endpoint ----------
@app.post("/ask")
def ask(body: AskBody):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    city = (body.city or DEFAULT_CITY).strip() if (body.city or DEFAULT_CITY) else "Tirana"

    # 1) ORA / DATA -> gjithmonë lokale, jo AI
    if is_time_question(text):
        dt = now_local()
        return {"ok": True, "answer": f"Ora tani në Tiranë është {format_datetime_sq(dt)}."}

    # 2) MATEMATIKË -> lokale, e saktë
    if is_math_question(text):
        expr = extract_math_expr(text)
        if not expr:
            return {"ok": True, "answer": "Ma jep shprehjen matematikore tamam (p.sh. 28*17)."}
        try:
            val = safe_eval_math(expr)
        except ValueError:
            return {"ok": True, "answer": "S’e lexova dot shprehjen. Shkruaje thjesht p.sh. 28*17."}
        # formati: nëse është numër i plotë, pa presje
        if abs(val - round(val)) < 1e-12:
            return {"ok": True, "answer": str(int(round(val)))}
        return {"ok": True, "answer": str(val)}

    # 3) MOTI -> lokale via OpenWeather
    if is_weather_question(text):
        w = get_weather(city)
        if not w:
            return {"ok": True, "answer": "S’po marr dot motin tani. Kontrollo OPENWEATHER_API_KEY ose qytetin."}
        return {"ok": True, "answer": w}

    # 4) TRAFIKU -> pa API s’ka “live”. Të paktën mos shpik.
    if is_traffic_question(text):
        return {
            "ok": True,
            "answer": "Për trafik live duhen të dhëna reale (Google Maps/Distance Matrix). "
                      "Më thuaj nga ku → ku, dhe orën kur do nisësh, edhe ta lidhim me API."
        }

    # 5) Gjithçka tjetër -> AI
    # i japim edhe context minimal (ora aktuale) POR jo që të shpikë, vetëm si info.
    dt = now_local()
    context = f"Context: Lokacioni: Tirana. Data/ora lokale: {format_datetime_sq(dt)}."
    prompt = f"{context}\n\nPyetja e userit: {text}"

    answer = ask_llm(prompt)
    return {"ok": True, "answer": answer}


@app.get("/weather")
def weather(city: str = "Tirana"):
    w = get_weather(city)
    if not w:
        raise HTTPException(status_code=400, detail="Weather not available")
    return {"ok": True, "answer": w}
