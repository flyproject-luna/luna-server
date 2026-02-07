import os
import re
import ast
import math
import requests
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()

MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()

app = FastAPI()


class AskBody(BaseModel):
    text: str
    city: str | None = None
    name: str | None = None
    family: str | None = None
    device_id: str | None = None


@app.get("/")
def root():
    return "ok"


@app.get("/health")
def health():
    return {"ok": True, "time_utc": datetime.now(timezone.utc).isoformat()}


def get_weather(city: str) -> str | None:
    if not OPENWEATHER_API_KEY:
        return None
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric", "lang": "en"}
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        temp = data["main"]["temp"]
        hum = data["main"]["humidity"]
        wind = data["wind"]["speed"]
        desc = data["weather"][0]["description"]
        return f"Weather in {city}: {temp:.1f}°C, {desc}. Humidity {hum}%, wind {wind:.2f} m/s."
    except Exception:
        return None


# ---- Safe math (server-side fallback) ----
_ALLOWED_NODES = {
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Load, ast.Call, ast.Name
}
_ALLOWED_FUNCS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round
}
_ALLOWED_NAMES = {"pi": math.pi, "e": math.e}


def safe_eval_math(expr: str) -> str | None:
    expr = expr.strip()
    if not expr:
        return None
    # allow only basic chars
    if not re.fullmatch(r"[0-9\.\+\-\*\/\%\(\)\s\^a-zA-Z_]+", expr):
        return None
    expr = expr.replace("^", "**")

    try:
        node = ast.parse(expr, mode="eval")
        for n in ast.walk(node):
            if type(n) not in _ALLOWED_NODES:
                return None
            if isinstance(n, ast.Call):
                if not isinstance(n.func, ast.Name):
                    return None
                if n.func.id not in _ALLOWED_FUNCS:
                    return None
            if isinstance(n, ast.Name):
                if n.id not in _ALLOWED_NAMES and n.id not in _ALLOWED_FUNCS:
                    return None

        code = compile(node, "<expr>", "eval")
        val = eval(code, {"__builtins__": {}}, {**_ALLOWED_FUNCS, **_ALLOWED_NAMES})
        return str(val)
    except Exception:
        return None


def ask_llm(prompt: str) -> str:
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY missing")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    system = (
        "You are Luna, a helpful Albanian AI assistant living in a smart clock device.\n"
        "Rules:\n"
        "- Be correct and practical.\n"
        "- If user asks math, answer exactly and only the result + short explanation.\n"
        "- If user asks for time/date, answer based on 'now' (current real time), not random dates.\n"
        "- If user asks for recipe, give ingredients + steps.\n"
        "- If something is missing (route for traffic etc.), ask ONE short question.\n"
        "- Keep answers short, friendly, and not robotic.\n"
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 350,
    }

    r = requests.post(url, headers=headers, json=payload, timeout=35)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OpenRouter error: {r.text}")

    data = r.json()
    return data["choices"][0]["message"]["content"].strip()


@app.post("/ask")
def ask(body: AskBody):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    # Server-side quick math fallback (optional)
    math_ans = safe_eval_math(text)
    if math_ans is not None:
        return {"ok": True, "answer": f"{math_ans}"}

    name = (body.name or "").strip()
    city = (body.city or "").strip()
    family = (body.family or "").strip()

    ctx = []
    if name:
        ctx.append(f"User name: {name}")
    if city:
        ctx.append(f"User city: {city}")
    if family:
        ctx.append(f"Family: {family}")

    w = None
    if city:
        w = get_weather(city)
        if w:
            ctx.append(w)

    context_block = ""
    if ctx:
        context_block = "\n\nContext:\n- " + "\n- ".join(ctx) + "\n"

    answer = ask_llm(text + context_block)
    return {"ok": True, "answer": answer}


@app.get("/weather")
def weather(city: str = "Tirana"):
    w = get_weather(city)
    if not w:
        raise HTTPException(status_code=400, detail="Weather not available")
    return {"ok": True, "answer": w}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
