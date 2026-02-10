import os
import re
import ast
import math
import requests
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# --------------------- KONFIGURIMI ---------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()

# Model FALAS dhe AKTIV në Groq (shkurt 2026) – super i shpejtë dhe me limite të larta
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

app = FastAPI(title="Luna Server – Groq Free Tier (llama-3.1-8b-instant)")

class AskBody(BaseModel):
    text: str
    city: str | None = None
    name: str | None = None
    family: str | None = None
    device_id: str | None = None


@app.get("/")
def root():
    return {"status": "ok", "message": f"Luna Server po punon me {GROQ_MODEL} (falas & i shpejtë)"}


@app.get("/health")
def health():
    return {
        "ok": True,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "groq_model": GROQ_MODEL,
        "weather_key_set": bool(OPENWEATHER_API_KEY)
    }


def get_weather(city: str) -> str | None:
    if not OPENWEATHER_API_KEY:
        return None
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric", "lang": "sq"}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        temp = data["main"]["temp"]
        hum = data["main"]["humidity"]
        wind = data["wind"]["speed"]
        desc = data["weather"][0]["description"]
        return f"Moti në {city}: {temp:.1f}°C, {desc}. Lagështia {hum}%, era {wind:.2f} m/s."
    except Exception:
        return None


# Math i sigurt lokal (fallback)
_ALLOWED_NODES = {ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant,
                  ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
                  ast.USub, ast.UAdd, ast.Load, ast.Call, ast.Name}
_ALLOWED_FUNCS = {"sqrt": math.sqrt, "abs": abs, "round": round}
_ALLOWED_NAMES = {"pi": math.pi, "e": math.e}

def safe_eval_math(expr: str) -> str | None:
    expr = expr.strip()
    if not expr or not re.fullmatch(r"[0-9\.\+\-\*\/\%\(\)\s\^a-zA-Z_]+", expr):
        return None
    expr = expr.replace("^", "**")
    try:
        node = ast.parse(expr, mode="eval")
        for n in ast.walk(node):
            if type(n) not in _ALLOWED_NODES:
                return None
            if isinstance(n, ast.Call) and (not isinstance(n.func, ast.Name) or n.func.id not in _ALLOWED_FUNCS):
                return None
            if isinstance(n, ast.Name) and n.id not in _ALLOWED_NAMES and n.id not in _ALLOWED_FUNCS:
                return None
        code = compile(node, "<expr>", "eval")
        val = eval(code, {"__builtins__": {}}, {**_ALLOWED_FUNCS, **_ALLOWED_NAMES})
        return str(val)
    except Exception:
        return None


def ask_groq(prompt: str) -> str:
    if not GROQ_API_KEY:
        raise HTTPException(500, "GROQ_API_KEY mungon – shtoje në env të Railway")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    system_prompt = (
        "Ti je Luna, një asistent miqësor dhe i zgjuar shqip në një orë smart ose altoparlant.\n"
        "Përgjigju gjithmonë në shqip, natyrshëm, konciz dhe si një mik.\n"
        "Për matematikë: jep vetëm rezultat + shpjegim të shkurtër.\n"
        "Për orë/datë: përdor kohën reale.\n"
        "Për receta: përbërës + hapa të qartë.\n"
        "Nëse mungon diçka: pyet vetëm një pyetje të shkurtër.\n"
        "Mos u bëj robotik – fol normal."
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.6,
        "max_tokens": 350,
    }

    try:
        r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except requests.exceptions.RequestException as e:
        raise HTTPException(502, f"Gabim me Groq API: {str(e)}")


@app.post("/ask")
def ask(body: AskBody):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "Teksti është bosh")

    # Math fallback
    math_ans = safe_eval_math(text)
    if math_ans is not None:
        return {"ok": True, "answer": math_ans}

    # Konteksti
    ctx = []
    if body.name:
        ctx.append(f"Emri i përdoruesit: {body.name.strip()}")
    if body.city:
        ctx.append(f"Qyteti: {body.city.strip()}")
    if body.family:
        ctx.append(f"Familja: {body.family.strip()}")

    weather = None
    if body.city:
        weather = get_weather(body.city.strip())
        if weather:
            ctx.append(weather)

    context_block = "\n\nKonteksti:\n" + "\n".join(f"- {line}" for line in ctx) + "\n" if ctx else ""

    full_prompt = text + context_block

    # Thirrja te Groq
    try:
        answer = ask_groq(full_prompt)
        return {"ok": True, "answer": answer}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(500, f"Gabim server: {str(e)}")


@app.get("/weather")
def weather(city: str = "Tirana"):
    w = get_weather(city)
    if not w:
        raise HTTPException(400, "Moti nuk u gjet")
    return {"ok": True, "answer": w}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
