import os
import requests
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict

# ---------------- CONFIG ----------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MODEL = "llama-3.3-70b-8192"

app = FastAPI(title="Luna AI Memory Core")

# Memoria e bisedave: { "mac_address": [historia_e_mesazheve] }
bisedat: Dict[str, List[Dict]] = {}

class AskBody(BaseModel):
    text: str
    device_id: Optional[str] = "unknown_device"
    city: Optional[str] = "Tirana"

# ---------------- LOGJIKA LOKALE ----------------
def kontrolli_lokal(text: str):
    text_clean = text.lower().strip()
    
    # 1. Filtri i mirësjelljes
    if any(fjale in text_clean for fjale in ["budall", "peder", "idiot", "muta"]):
        return "Unë jam Luna dhe jam programuar të jem e sjellshme. Ju lutem flisni me edukatë."
    
    # 2. Pyetjet rutinë (pa AI)
    if "ora" in text_clean and "sa" in text_clean:
        return f"Ora është fiks {datetime.now().strftime('%H:%M')}."
    
    if text_clean in ["luna", "hej luna", "tung"]:
        return "Po, të dëgjoj! Si mund të të ndihmoj?"

    return None

# ---------------- AI CORE ME HISTORIK ----------------
def ask_groq_with_memory(prompt: str, device_id: str, qyteti: str):
    # Krijo historikun e ri nëse pajisja lidhet për herë të parë
    if device_id not in bisedat:
        bisedat[device_id] = [
            {"role": "system", "content": f"Ti je Luna, asistente inteligjente shqiptare në {qyteti}. Përgjigju shkurt, shqip dhe mbaj mend bisedën."}
        ]
    
    # Shto pyetjen e përdoruesit në memorie
    bisedat[device_id].append({"role": "user", "content": prompt})
    
    # Limito memorien (System message + 10 mesazhet e fundit)
    if len(bisedat[device_id]) > 11:
        bisedat[device_id] = [bisedat[device_id][0]] + bisedat[device_id][-10:]

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL,
        "messages": bisedat[device_id], # Dërgojmë gjithë historikun te Groq
        "temperature": 0.6,
        "max_tokens": 200
    }

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=12
        )
        r.raise_for_status()
        pergjigja = r.json()["choices"][0]["message"]["content"].strip()
        
        # Ruaj përgjigjen e AI në memorie për kontekstin e ardhshëm
        bisedat[device_id].append({"role": "assistant", "content": pergjigja})
        
        return pergjigja
    except Exception as e:
        print(f"Error: {e}")
        return "Më fal, u shkëput lidhja me memorien time."

# ---------------- ENDPOINTS ----------------
@app.post("/ask")
async def ask(body: AskBody):
    if not body.text.strip():
        return {"ok": False, "answer": "Nuk dëgjova asgjë."}

    # Provo logjikën lokale (më e shpejtë)
    lokal = kontrolli_lokal(body.text)
    if lokal:
        return {"ok": True, "answer": lokal}

    # Përndryshe, pyet Groq me memorie
    answer = ask_groq_with_memory(body.text, body.device_id, body.city)
    return {"ok": True, "answer": answer}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
