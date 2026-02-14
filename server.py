import os
import requests
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict

# ---------------- CONFIG ----------------
# Sigurohu që GROQ_API_KEY ta kesh te Railway -> Variables
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

# Përdorim këtë model që është më i fundit dhe më i qëndrueshmi në Groq
MODEL_AI = "llama-3.3-70b-versatile"

app = FastAPI(title="Luna AI Memory Core v2.0")

# Memoria në RAM: { "mac_address": [historia] }
bisedat: Dict[str, List[Dict]] = {}

class AskBody(BaseModel):
    text: str
    device_id: Optional[str] = "unknown_device"
    city: Optional[str] = "Tirana"

# ---------------- LOGJIKA LOKALE ----------------
def kontrolli_lokal(text: str):
    text_clean = text.lower().strip()
    
    # Filtri i fjalorit
    fjalet_e_kqija = ["budall", "peder", "idiot", "muta", "pjerth"]
    if any(fjale in text_clean for fjale in fjalet_e_kqija):
        return "Unë jam Luna dhe komunikoj vetëm me etikë dhe edukatë."
    
    # Pyetje për kohën
    if "ora" in text_clean and "sa" in text_clean:
        tani = datetime.now().strftime("%H:%M")
        return f"Ora në Shqipëri është fiks {tani}."

    if "data" in text_clean or "sot data" in text_clean:
        sot = datetime.now().strftime("%d/%m/%Y")
        return f"Sot është data {sot}."

    return None

# ---------------- AI CORE ME MEMORIE ----------------
def ask_groq_with_memory(prompt: str, device_id: str, qyteti: str):
    # Kontrolli i API Key
    if not GROQ_API_KEY:
        print("KRIZË: GROQ_API_KEY nuk është gjetur në Variables!")
        return "Më fal, por pronari im nuk ka vendosur çelësin tim të inteligjencës."

    # Inicializimi i memories për pajisjen e re
    if device_id not in bisedat:
        bisedat[device_id] = [
            {
                "role": "system", 
                "content": f"Ti je Luna, një asistente inteligjente shqiptare në {qyteti}. Përgjigju gjithmonë shqip, shkurt dhe me mirësjellje. Mbaj mend emrin e përdoruesit nëse ta thotë."
            }
        ]
    
    # Shto pyetjen e përdoruesit
    bisedat[device_id].append({"role": "user", "content": prompt})
    
    # Limito memorien në 8 mesazhet e fundit për të mos rënduar kërkesën
    if len(bisedat[device_id]) > 9:
        bisedat[device_id] = [bisedat[device_id][0]] + bisedat[device_id][-8:]

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL_AI,
        "messages": bisedat[device_id],
        "temperature": 0.7,
        "max_tokens": 200
    }

    try:
        print(f"Duke dërguar kërkesën për {device_id} te Groq...")
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=12
        )
        
        # Debugging nëse Groq kthen gabim
        if r.status_code != 200:
            print(f"GABIM NGA GROQ ({r.status_code}): {r.text}")
            return f"Gabim nga truri im cloud (Kodi {r.status_code})."

        pergjigja = r.json()["choices"][0]["message"]["content"].strip()
        
        # Ruaj përgjigjen e AI në memorie
        bisedat[device_id].append({"role": "assistant", "content": pergjigja})
        return pergjigja

    except Exception as e:
        print(f"EXCEPTION: {str(e)}")
        return "Pati një problem teknik me procesimin e bisedës."

# ---------------- ENDPOINTS ----------------

@app.get("/")
def health_check():
    return {"status": "Luna is online", "memory_active": True}

@app.post("/ask")
async def ask(body: AskBody):
    # 1. Kontrolli i tekstit bosh
    if not body.text or len(body.text.strip()) == 0:
        return {"ok": False, "answer": "Nuk dëgjova asgjë."}

    # 2. Kontrollo logjikën lokale (kursen kohë dhe para)
    lokal = kontrolli_lokal(body.text)
    if lokal:
        return {"ok": True, "answer": lokal}

    # 3. Thirr inteligjencën Groq me memorie
    answer = ask_groq_with_memory(body.text, body.device_id, body.city)
    return {"ok": True, "answer": answer}

if __name__ == "__main__":
    import uvicorn
    # Railway përdor variablën PORT
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
