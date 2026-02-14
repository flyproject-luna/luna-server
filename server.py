import os
from gtts import gTTS
from fastapi.responses import FileResponse

# ... pjesa tjetër e kodit (Groq, Moti etj.) ...

@app.post("/ask")
async def ask(body: AskBody):
    # 1. Merr tekstin nga Luna (ashtu siç e bëmë radhën e kaluar)
    luna_text = ask_luna_logic(body.text, body.device_id) 

    # 2. Gjenero audion në Shqip
    audio_filename = "luna_voice.mp3"
    tts = gTTS(text=luna_text, lang='sq')
    tts.save(audio_filename)

    # 3. Kthe përgjigjen
    # ESP32 do të lexojë "answer" për tekstin dhe do të shkojë te 
    # linku i audios për ta shkarkuar dhe luajtur në boks
    return {
        "ok": True, 
        "answer": luna_text, 
        "audio_url": f"https://{os.getenv('RAILWAY_STATIC_URL')}/get_audio"
    }

@app.get("/get_audio")
async def get_audio():
    # Ky endpoint dërgon skedarin MP3 te ESP32
    return FileResponse("luna_voice.mp3", media_type="audio/mpeg")
