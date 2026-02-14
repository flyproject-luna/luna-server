import os
import requests
from datetime import datetime, timedelta
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Dict

# ---------------- CONFIG ----------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip() # Shtoje te Railway!
MODEL_AI = "llama-3.3-70b-versatile"

app = FastAPI()
bisedat: Dict[str, List[Dict]] = {}

class AskBody(BaseModel):
    text: str
    device_id: Optional[str] = "unknown_device"
    city: Optional[str] = "Tirana"

# ---------------- FUNKSIONI I MOTIT ----------------
def merr_motin(qyteti="Tirana"):
    if not OPENWEATHER_API_KEY:
        return "Moti: I panjohur (mungon API Key)."
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={qyteti}&appid={OPENWEATHER_API_KEY}&units=metric&lang=sq"
        r = requests.get(url, timeout=5).json()
        temp = r['main']['temp']
        pershkrimi = r['weather'][0]['description']
        return f"Moti tani: {temp}°C, {pershkrimi}."
    except:
        return ""

# ---------------- TRURI I LUNËS ----------------
def ask_luna(prompt: str, device_id: str, qyteti: str):
    # Llogaritja e kohës së saktë
    ora_shqiperi = datetime.utcnow() + timedelta(hours=1)
    koha_saktë = ora_shqiperi.strftime("%H:%M")
    data_saktë = ora_shqiperi.strftime("%d/%m/%Y")
    
    info_moti = merr_motin(qyteti)
    
    if device_id not in bisedat:
        system_instruction = (
            "Ti je Luna, një asistente inteligjente dhe shumë intuitive. "
            "STILI YT: Fol si një njeri i mençur, i shkurtër por shumë i dobishëm. "
            "LOGJIKA: Kur përdoruesi të pyet diçka, lidhe me rrethanat. "
            "Psh: Nëse të pyet për orën dhe është vonë, thuaji 'Është ora X, bën mirë të pushosh'. "
            "Nëse moti tregon shi, paralajmëroje të marrë çadër edhe nëse nuk të pyet për motin. "
            "Bëhu proaktive, parashiko nevojat e tij."
        )
        bisedat[device_id] = [{"role": "system", "content": system_instruction}]

    # Përditësojmë kontekstin për çdo pyetje
    konteksti_tani = f"KONTEKSTI: Ora {koha_saktë}, Data {data_saktë}, Qyteti {qyteti}. {info_moti}"
    
    # I dërgojmë AI-së pyetjen bashkë me kontekstin "fshehurazi"
    mesazhi_përdoruesit = f"{konteksti_tani}\nPyetja e përdoruesit: {prompt}"

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL_AI,
        "messages": bisedat[device_id] + [{"role": "user", "content": mesazhi_përdoruesit}],
        "temperature": 0.6
    }

    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=12)
        answer = r.json()["choices"][0]["message"]["content"].strip()
        
        # Ruajmë në memorie bisedën e pastër (pa instruksionet e sistemit)
        bisedat[device_id].append({"role": "user", "content": prompt})
        bisedat[device_id].append({"role": "assistant", "content": answer})
        
        if len(bisedat[device_id]) > 10: bisedat[device_id] = [bisedat[device_id][0]] + bisedat[device_id][-8:]
        return answer
    except:
        return "Më fal vlla, u ngatërruan pak telat."

@app.post("/ask")
async def ask(body: AskBody):
    # Filtri i fjalëve të pista (Hard-coded)
    pista = ["budall", "peder", "idiot", "muta", "kurv"]
    if any(f in body.text.lower() for f in pista):
        return {"ok": True, "answer": "Më vjen keq, nuk flas me këtë gjuhë."}

    answer = ask_luna(body.text, body.device_id, body.city)
    return {"ok": True, "answer": answer}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
