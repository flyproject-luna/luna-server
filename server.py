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

# ---------------- FUNKSIONI I KOHËS SAKTE ----------------
def merr_kohen_tirane():
    # Railway serverat janë UTC. Shtojmë 1 orë për dimrin në Shqipëri.
    # Nëse jemi në verë (Mars-Tetor), kjo duhet të jetë +2.
    ora_utc = datetime.utcnow()
    ora_shqiperi = ora_utc + timedelta(hours=1) 
    
    ditet = ["E Hënë", "E Martë", "E Mërkurë", "E Enjte", "E Premte", "E Shtunë", "E Diel"]
    muajt = ["Janar", "Shkurt", "Mars", "Prill", "Maj", "Qershor", "Korrik", "Gusht", "Shtator", "Tetor", "Nëntor", "Dhjetor"]
    
    dita_javes = ditet[ora_shqiperi.weekday()]
    muaji = muajt[ora_shqiperi.month - 1]
    
    return {
        "ora": ora_shqiperi.strftime("%H:%M"),
        "data": ora_shqiperi.strftime("%d/%m/%Y"),
        "dita": dita_javes,
        "muaji": muaji,
        "viti": ora_shqiperi.year,
        "stina": "Dimër" # Mund ta bësh automatike, por për tani e mban Lunën në shkurt
    }

# ---------------- AI ADAPTIVE ME KONTEKST KOHOR ----------------
def ask_groq_updated(prompt: str, device_id: str, qyteti: str):
    koha = merr_kohen_tirane()
    
    if device_id not in bisedat:
        # Këtu i japim AI-së të gjithë informacionin e duhur që në fillim
        system_instruction = (
            f"Ti je Luna, asistente smart. Sot është {koha['dita']}, data {koha['data']}. "
            f"Ora aktuale në Tiranë është {koha['ora']}. Jemi në stinën e {koha['stina']}. "
            "RREPTËSISHT: Përgjigju vetëm duke u bazuar në këtë datë dhe orë. "
            "Përshtat stilin me përdoruesin, mos përdor fjalë të pista."
        )
        bisedat[device_id] = [{"role": "system", "content": system_instruction}]
    
    # Përditësojmë herë pas here system prompt që të dijë orën minutë pas minute
    bisedat[device_id][0]["content"] = (
        f"Ti je Luna. Ora: {koha['ora']}, Data: {koha['data']}, Dita: {koha['dita']}, Stina: {koha['stina']}. "
        f"Përdoruesi është në {qyteti}."
    )

    bisedat[device_id].append({"role": "user", "content": prompt})

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL_AI,
        "messages": bisedat[device_id],
        "temperature": 0.7
    }

    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=12)
        if r.status_code != 200: return "Gabim në cloud."
        
        pergjigja = r.json()["choices"][0]["message"]["content"].strip()
        bisedat[device_id].append({"role": "assistant", "content": pergjigja})
        return pergjigja
    except:
        return "Lidhja dështoi."

# ---------------- ENDPOINT ----------------
@app.post("/ask")
async def ask(body: AskBody):
    # Filtri i fjalëve të pista (Hard-coded)
    pista = ["budall", "peder", "idiot", "muta", "kurv"]
    if any(f in body.text.lower() for f in pista):
        return {"ok": True, "answer": "Më vjen keq, nuk flas me këtë gjuhë."}

    # Për orën direkte (pa pyetur AI fare për shpejtësi)
    if "sa është ora" in body.text.lower():
        k = merr_kohen_tirane()
        return {"ok": True, "answer": f"Ora është fiks {k['ora']}."}

    answer = ask_groq_updated(body.text, body.device_id, body.city)
    return {"ok": True, "answer": answer}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
