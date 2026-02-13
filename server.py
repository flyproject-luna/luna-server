import os
import requests
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

# ---------------- CONFIG ----------------
# Sigurohu që këto t'i kesh shtuar te "Variables" në Railway
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "CHELSI_JUAJ_KETU").strip()
MODEL = "llama3-70b-8192"

app = FastAPI(title="Luna AI Core")

class AskBody(BaseModel):
    text: str
    city: Optional[str] = "Tirana"

# ---------------- LOGJIKA LOKALE ----------------
def kontrolli_lokal(text: str):
    text_clean = text.lower()
    
    # Fjalë banale (Mbrojtja lokale)
    fjalet_e_kqija = ["budall", "peder", "idiot"]
    if any(fjale in text_clean for fjale in fjalet_e_kqija):
        return "Unë jam programuar të jem e sjellshme. Ju lutem flisni me edukatë."
    
    # Ora lokale
    if "ora" in text_clean and "sa" in text_clean:
        return f"Ora në Shqipëri është {datetime.now().strftime('%H:%M')}."
    
    # Përshëndetja
    if text_clean in ["luna", "hej luna", "tung luna"]:
        return "Përshëndetje! Jam Luna, si mund t'ju ndihmoj sot?"

    return None

# ---------------- AI CORE ----------------
def ask_groq(prompt, qyteti):
    if not GROQ_API_KEY or GROQ_API_KEY == "CHELSI_JUAJ_KETU":
        return "Gabim: Mungon Groq API Key në server."

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_msg = f"Ti je Luna, asistente smart. Ndodhesh në {qyteti}. Përgjigju shkurt e shqip."
    
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.6
    }

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=10
        )
        r.raise_for_status() # Kjo kap gabimet 401, 404, 500
        return r.json()["choices"][0]["message"]["content"]
    except requests.exceptions.HTTPError as e:
        return f"Gabim nga Groq: {e.response.status_code}"
    except Exception as e:
        print(f"Error: {e}")
        return "Pati një problem me procesimin e kërkesës."

# ---------------- ENDPOINT ----------------
@app.post("/ask")
async def ask(body: AskBody):
    # 1. Kontrollo nëse teksti është bosh
    if not body.text or len(body.text.strip()) == 0:
        return {"ok": False, "answer": "Nuk dëgjova asgjë."}

    # 2. Kontrollo lokalisht (Kursen kohë dhe parandalon 502)
    pergjigje = kontrolli_lokal(body.text)
    if pergjigje:
        return {"ok": True, "answer": pergjigje}

    # 3. Nëse nuk është pyetje rutinë, thirr AI
    ai_answer = ask_groq(body.text, body.city)
    return {"ok": True, "answer": ai_answer}

if __name__ == "__main__":
    import uvicorn
    # Railway kërkon PORT nga environment variables
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
