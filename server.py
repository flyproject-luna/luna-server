import os
import requests
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict

# ---------------- CONFIG ----------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MODEL_AI = "llama-3.3-70b-versatile"

app = FastAPI(title="Luna AI Adaptive")

# Memoria në RAM
bisedat: Dict[str, List[Dict]] = {}

class AskBody(BaseModel):
    text: str
    device_id: Optional[str] = "unknown_device"
    city: Optional[str] = "Tirana"

# ---------------- FILTRI I MENJËHERSHËM ----------------
def kontrolli_sigurie(text: str):
    text_clean = text.lower().strip()
    
    # Lista e fjalëve që bllokohen menjëherë
    FJALE_TE_PISTA = ["budall", "peder", "idiot", "muta", "pjerth", "kurv", "qen"] 
    
    if any(fjale in text_clean for fjale in FJALE_TE_PISTA):
        return True
    return False

# ---------------- AI CORE ME ADAPTIM STILI ----------------
def ask_groq_adaptive(prompt: str, device_id: str, qyteti: str):
    if not GROQ_API_KEY:
        return "Konfigurimi i API-t mungon."

    if device_id not in bisedat:
        # Instruksionet për stilin dhe pasqyrimin
        system_instruction = (
            f"Ti je Luna, një asistente inteligjente shqiptare në {qyteti}. "
            "RREGULLI KYÇ: Përshtat stilin tënd me atë të përdoruesit. "
            "Nëse përdoruesi flet shkurt dhe me zhargon, përgjigju shkurt. "
            "Nëse ai flet me edukatë dhe fjali të gjata, bëhu më formale. "
            "Mos përdor kurrë fjalë fyese dhe mbaj ton miqësor por të matur."
        )
        bisedat[device_id] = [{"role": "system", "content": system_instruction}]
    
    # Shto pyetjen e përdoruesit
    bisedat[device_id].append({"role": "user", "content": prompt})
    
    # Limito memorien
    if len(bisedat[device_id]) > 11:
        bisedat[device_id] = [bisedat[device_id][0]] + bisedat[device_id][-10:]

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL_AI,
        "messages": bisedat[device_id],
        "temperature": 0.8, # Pak më e lartë për të lejuar kreativitet në stil
        "max_tokens": 150
    }

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=12
        )
        
        if r.status_code != 200:
            print(f"DEBUG ERROR: {r.text}")
            return "Pati një pengesë në procesim."

        pergjigja = r.json()["choices"][0]["message"]["content"].strip()
        bisedat[device_id].append({"role": "assistant", "content": pergjigja})
        return pergjigja

    except Exception as e:
        print(f"LOG: {str(e)}")
        return "Lidhja u ndërpre."

# ---------------- ENDPOINTS ----------------

@app.post("/ask")
async def ask(body: AskBody):
    # 1. Filtri i menjëhershëm për fjalë të pista
    if kontrolli_sigurie(body.text):
        return {"ok": True, "answer": "Më vjen keq, por nuk mund të komunikoj me këtë gjuhë."}

    # 2. Logjika rutinë (Ora)
    if "ora" in body.text.lower() and "sa" in body.text.lower():
        return {"ok": True, "answer": f"Ora është {datetime.now().strftime('%H:%M')}."}

    # 3. AI Adaptive
    answer = ask_groq_adaptive(body.text, body.device_id, body.city)
    return {"ok": True, "answer": answer}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
