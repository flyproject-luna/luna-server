import os
import requests
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

# ---------------- CONFIG ----------------
GROQ_API_KEY = "CHELSI_JUAJ_KETU" 
MODEL = "llama3-70b-8192"

app = FastAPI(title="Luna AI Core")

# Lista e qyteteve për validim lokal
QYTETET_SHQIPERI = ["tirana", "durres", "vlore", "shkoder", "fier", "korce", "berat", "elbasan", "sarande", "kukes"]
FJALE_BANALE = ["budall", "peder", "muta", "idiot"] # Shto të tjera këtu

class AskBody(BaseModel):
    text: str
    city: Optional[str] = "Tirana"

# ---------------- LOGJIKA LOKALE ----------------

def kontrolli_lokal(text: str):
    text_clean = text.lower()
    
    # 1. Filtri i fjalorit
    if any(fjale in text_clean for fjale in FJALE_BANALE):
        return "Më vjen keq, por unë komunikoj vetëm me edukatë."
    
    # 2. Pyetjet për orën
    if "sa është ora" in text_clean or "ora tani" in text_clean:
        tani = datetime.now().strftime("%H:%M")
        return f"Ora është fiks {tani}."
    
    # 3. Përshëndetja Luna
    if text_clean == "luna" or text_clean == "hej luna":
        return "Po, të dëgjoj! Si mund të të ndihmoj?"

    return None

# ---------------- AI CORE ----------------

def ask_groq(prompt, qyteti):
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    
    system_prompt = (
        f"Ti je Luna, një asistente smart shqiptare. Përgjigju shkurt (max 2 fjali). "
        f"Përdoruesi ndodhet në {qyteti}. Fol në mënyrë natyrale, jo si robot."
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5
    }

    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=10)
        return r.json()["choices"][0]["message"]["content"]
    except:
        return "Pati një problem me lidhjen time në cloud."

# ---------------- ENDPOINT ----------------

@app.post("/ask")
async def ask(body: AskBody):
    if not body.text.strip():
        raise HTTPException(400, "Tekst bosh")

    # Kontrollo fillimisht lokalisht (Kursen kohë/API)
    pergjigje_lokale = kontrolli_lokal(body.text)
    if pergjigje_lokale:
        return {"ok": True, "answer": pergjigje_lokale, "source": "local"}

    # Nëse nuk është pyetje rutinë, pyet AI-në
    ai_answer = ask_groq(body.text, body.city)
    return {"ok": True, "answer": ai_answer, "source": "cloud"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
