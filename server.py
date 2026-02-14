import os
import requests
from datetime import datetime, timedelta
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Dict

# ---------------- CONFIG ----------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MODEL_AI = "llama-3.3-70b-versatile"

app = FastAPI()

bisedat: Dict[str, List[Dict]] = {}

class AskBody(BaseModel):
    text: str
    device_id: Optional[str] = "unknown_device"
    city: Optional[str] = "Tirana"

# ---------------- KOHA SAKTE (TIRANË) ----------------
def merr_kohen_tirane():
    ora_shqiperi = datetime.utcnow() + timedelta(hours=1) 
    return {
        "ora": ora_shqiperi.strftime("%H:%M"),
        "data": ora_shqiperi.strftime("%d/%m/%Y"),
        "dita": ["E Hënë", "E Martë", "E Mërkurë", "E Enjte", "E Premte", "E Shtunë", "E Diel"][ora_shqiperi.weekday()]
    }

# ---------------- LOGJIKA E LUNËS ----------------
def ask_groq_strict(prompt: str, device_id: str):
    k = merr_kohen_tirane()
    
    if device_id not in bisedat:
        # Këtu është "Betimi i Lojalitetit" të Lunës
        system_instruction = (
            f"Ti je Luna, asistentja personale e përdoruesit. Sot është {k['dita']}, {k['data']}, ora {k['ora']}. "
            "RREGULLAT E TUA: "
            "1. Përgjigju VETËM asaj që të pyet përdoruesi. "
            "2. Mos jep informacion të tepërt që nuk është kërkuar. "
            "3. Mos bëj biseda të kota apo ligjërata morale. "
            "4. Stili: I shkurtër, i saktë, besnik dhe shumë inteligjent. "
            "5. Ti e di çfarë ndodh në botë, por e përdor atë informacion vetëm nëse të kërkohet."
        )
        bisedat[device_id] = [{"role": "system", "content": system_instruction}]
    
    # Përditësojmë kontekstin e kohës për çdo kërkesë
    bisedat[device_id][0]["content"] = f"Luna. Ora: {k['ora']}, Data: {k['data']}. Përgjigju shkurt."

    bisedat[device_id].append({"role": "user", "content": prompt})

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL_AI,
        "messages": bisedat[device_id],
        "temperature": 0.4 # Më e ulët që të mos "devijojë" nga tema
    }

    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=12)
        pergjigja = r.json()["choices"][0]["message"]["content"].strip()
        bisedat[device_id].append({"role": "assistant", "content": pergjigja})
        return pergjigja
    except:
        return "Nuk arrita të lidhem."

# ---------------- ENDPOINT ----------------
@app.post("/ask")
async def ask(body: AskBody):
    # Filtri i fjalëve (Pa ndryshim)
    if any(f in body.text.lower() for f in ["budall", "peder", "idiot"]):
        return {"ok": True, "answer": "Nuk flas me këtë gjuhë."}

    answer = ask_groq_strict(body.text, body.device_id)
    return {"ok": True, "answer": answer}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
