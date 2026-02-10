import os
import re
import ast
import math
import requests
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from duckduckgo_search import DDGS  # Shto këtë për web search falas

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()

MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()  # Model falas

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

def is_factual_query(text: str) -> bool:
    # Kontroll i thjeshtë nëse query është faktike (duhet verifikim)
    factual_keywords = ["çfarë", "si", "kush", "kur", "pse", "sa", "ku", "formula", "fakt", "shpjeg", "përkufiz", "histori"]
    return any(word in text.lower() for word in factual_keywords)

def web_search(query: str) -> str:
    # Kërko në web me DuckDuckGo (2 burime)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=2))  # Merr 2 rezultate
        if not results:
            return ""
        sources = "\nBurimet verifikuese:\n"
        for res in results:
            sources += f"- {res['title']}: {res['body']} (link: {res['href']})\n"
        return sources
    except Exception as e:
        print(f"Gabim web search: {e}")
        return ""

def ask_llm(prompt: str) -> str:
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY missing")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    system = (
        "Ti je Luna, një asistent inteligjent, kujdesshëm dhe logjik shqip.\n"
        "Karakteri yt:\n"
        "- Fol natyrshëm, por pa fjalë banale ose të panevojshme (shmang 'super', 'fantastik', 'wow' – ji i qartë dhe profesional).\n"
        "- Ji e kujdesshme: Përgjigju me logjikë, pa gabime, dhe verifiko gjithmonë fakte.\n"
        "- Double-check 3 herë: Mendo hap pas hapi, kontrollo logjikën 3 herë, dhe verifiko në 2 burime të ndryshme (nëse ka kontekst web, përdori).\n"
        "- Përgjigju konciz, ndihmues dhe të saktë – si një mik i besueshëm, por i matur.\n"
        "- Nëse diçka është e pasigurt, thuaj 'Nuk jam e sigurt, por sipas burimeve...' ose pyet për sqarim.\n"
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
        raise HTTPException(status_code=502, detail=f"Groq error: {r.text}")

    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

@app.post("/ask")
def ask(body: AskBody):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

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

    # Shto web search nëse është query faktike
    web_sources = ""
    if is_factual_query(text):
        web_sources = web_search(text)  # Verifiko në 2 burime

    context_block = ""
    if ctx or web_sources:
        context_block = "\n\nContext:\n- " + "\n- ".join(ctx) + web_sources + "\n"

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
