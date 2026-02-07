import os
import time
from typing import Optional, Dict, Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


APP_NAME = "luna-server"
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "Tirana")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "openai/gpt-4o-mini")

# Cache i thjeshtë për motin
_weather_cache: Dict[str, Any] = {"ts": 0, "city": "", "data": None}
WEATHER_CACHE_SECONDS = 60


app = FastAPI(title=APP_NAME)


class AskRequest(BaseModel):
    device_id: Optional[str] = None
    question: str
    city: Optional[str] = None
    lang: Optional[str] = "sq"   # sq/en
    context: Optional[str] = None


class AskResponse(BaseModel):
    ok: bool
    answer: str


class WeatherResponse(BaseModel):
    ok: bool
    city: str
    temp_c: float
    description: str
    humidity: int
    wind_m_s: float


@app.get("/")
def root():
    return "ok"


@app.get("/health")
def health():
    return {"ok": True, "service": APP_NAME, "ts": int(time.time())}


def _require_env(name: str, value: str):
    if not value:
        raise HTTPException(status_code=500, detail=f"Missing env var: {name}")


async def _get_weather(city: str) -> WeatherResponse:
    _require_env("OPENWEATHER_API_KEY", OPENWEATHER_API_KEY)

    now = time.time()
    if (
        _weather_cache["data"] is not None
        and _weather_cache["city"].lower() == city.lower()
        and (now - _weather_cache["ts"]) < WEATHER_CACHE_SECONDS
    ):
        return _weather_cache["data"]

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"}

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, params=params)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"OpenWeather error: {r.text}")
        data = r.json()

    resp = WeatherResponse(
        ok=True,
        city=city,
        temp_c=float(data["main"]["temp"]),
        description=str(data["weather"][0]["description"]),
        humidity=int(data["main"]["humidity"]),
        wind_m_s=float(data["wind"]["speed"]),
    )

    _weather_cache["ts"] = now
    _weather_cache["city"] = city
    _weather_cache["data"] = resp
    return resp


@app.get("/weather", response_model=WeatherResponse)
async def weather(city: str = DEFAULT_CITY):
    return await _get_weather(city)


def _system_prompt(lang: str) -> str:
    # Prompt i thjeshtë, praktik, “Luna style”
    if (lang or "sq").lower().startswith("en"):
        return (
            "You are Luna, a helpful voice assistant. "
            "Be concise, practical, and correct. "
            "If the user asks for math, compute it. If they ask for a recipe, give steps and ingredients. "
            "If you are unsure, say so and ask one short follow-up."
        )
    return (
        "Je Luna, asistente e dobishme. "
        "Jep përgjigje të shkurtra, të sakta, praktike. "
        "Nëse pyetja është matematikë, llogarit saktë. "
        "Nëse kërkon recetë, jep përbërësit dhe hapat. "
        "Nëse nuk je e sigurt, thuaje dhe bëj 1 pyetje të shkurtër."
    )


async def _ask_ai(question: str, lang: str, extra_context: Optional[str]) -> str:
    _require_env("OPENROUTER_API_KEY", OPENROUTER_API_KEY)

    # Pak kontekst “tool-less” (p.sh. moti i fundit)
    ctx = (extra_context or "").strip()
    if ctx:
        user_content = f"Context:\n{ctx}\n\nUser question:\n{question}"
    else:
        user_content = question

    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": _system_prompt(lang)},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.6,
        "max_tokens": 350,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        # këto janë opsionale:
        "HTTP-Referer": "https://luna.local",
        "X-Title": "luna-server",
    }

    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"AI error: {r.text}")
        data = r.json()

    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        raise HTTPException(status_code=502, detail="AI response parse error")


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Empty question")

    # Nëse user s’jep city, përdor default
    city = (req.city or DEFAULT_CITY).strip()

    # Nëse pyet për mot, fusim motin si context automatik
    # (shumë e dobishme për “çfarë të gatuaj sot” kur bie shi, etj.)
    context_parts = []
    if req.context:
        context_parts.append(req.context)

    lowered = q.lower()
    if any(k in lowered for k in ["moti", "weather", "shi", "temperatur", "era", "humidity", "lagësht"]):
        try:
            w = await _get_weather(city)
            context_parts.append(
                f"Weather in {w.city}: {w.temp_c}°C, {w.description}, humidity {w.humidity}%, wind {w.wind_m_s} m/s."
            )
        except Exception:
            pass

    answer = await _ask_ai(q, req.lang or "sq", "\n".join(context_parts) if context_parts else None)
    return AskResponse(ok=True, answer=answer)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, log_level="info")
