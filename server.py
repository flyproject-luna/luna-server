import os
import requests
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

# ---------------- CONFIG ----------------
# Sigurohu që këtë ta kesh te Railway -> Variables
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
# Modeli më i qëndrueshëm aktualisht
MODEL = "llama-3.3-70b-versatile"

app = FastAPI(title="Luna AI Core")

class AskBody(BaseModel):
    text: str
    city: Optional[str] = "Tirana"

# ---------------- LOGJIKA LOKALE ----------------
def kontrolli_lokal(text: str):
    text_clean = text.lower().strip()
    
    # 1. Filtri i mirësjelljes
    fjalet_e_kqija = ["budall", "peder", "idiot", "muta", "pjerth"]
    if any(fjale in text_clean for fjale in fjalet_e_kqija):
        return "Unë jam Luna dhe jam programuar të komunikoj vetëm me edukatë."
    
    # 2. Ora dhe Data (Lokale)
    if "ora" in text_clean and "sa" in text_clean:
        tani = datetime.now().strftime("%H:%M")
        return f"Ora në Tiranë është fiks {tani}."
    
    if "data" in text_clean or "data sot" in text_clean:
        sot = datetime.now().strftime("%d/%m/%Y")
        return f"Sot data është {sot}."
    
    # 3. Përshëndetja Luna
    if text_clean in ["luna", "hej luna", "tung luna", "ç'kemi luna"]:
        return "Përshëndetje! Jam Luna, asistenta jote shqiptare. Si mund të të ndihmoj?"

    return None

# ---------------- AI CORE ----------------
def ask_groq(prompt, qyteti):
    if not GROQ_API_KEY:
        return "Gabim: Mungon GROQ_API_KEY në server."

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Instruksione strikte për personalitetin e Lunës
    system_msg = (
        f"Ti je Luna, një asistente inteligjente shqiptare. "
        f"Ndodhesh në qytetin: {qyteti}. "
        "Përgjigju gjithmonë në gjuhën shqipe, shkurt (maksimumi 2 fjali) dhe me mençuri."
    )
    
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5,
        "max_tokens": 150
    }

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=10
        )
        
        if r.status_code != 200:
            print(f"DEBUG: Groq Error {r.status_code} - {r.text}")
            return f"Gabim nga AI (Kodi {r.status_code}). Provo përsëri."

        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"DEBUG: Exception - {str(e)}")
        return "U shkëput lidhja me trurin tim në cloud."

# ---------------- ENDPOINTS ----------------
@app.get("/")
def home():
    return {"status": "Luna is online", "time": datetime.now().isoformat()}

@app.post("/ask")
async def ask(body: AskBody):
    if not body.text.strip():
        return {"ok": False, "answer": "Nuk dëgjova asgjë."}

    # Kontrollo fillimisht filtrat lokalë
    pergjigje_lokale = kontrolli_lokal(body.text)
    if pergjigje_lokale:
        return {"ok": True, "answer": pergjigje_lokale}

    # Nëse s'është pyetje rutinë, thirr Groq
    ai_answer = ask_groq(body.text, body.city)
    return {"ok": True, "answer": ai_answer}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
