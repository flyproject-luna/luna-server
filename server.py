from flask import Flask, request, jsonify
import datetime

app = Flask(__name__)

@app.get("/")
def home():
    return "LUNA server running ✅"

@app.get("/ask")
def ask():
    q = request.args.get("q", "").lower().strip()
    if not q:
        return jsonify(ok=False, error="mungon parametri q"), 400

    # ORA
    if "ora" in q:
        now = datetime.datetime.now().strftime("%H:%M")
        return jsonify(ok=True, answer=f"Ora tani është {now}")

    # MOTI (placeholder – më vonë API reale)
    if "moti" in q:
        city = q.replace("moti ne", "").strip()
        if not city:
            city = "qytetin tend"
        return jsonify(ok=True, answer=f"Moti në {city} është me diell ☀️")

    # MUZIKË
    if "luaj" in q:
        song = q.replace("luaj", "").strip()
        return jsonify(
            ok=True,
            action="play_music",
            query=song,
            answer=f"Po luaj {song}"
        )

    # DEFAULT
    return jsonify(ok=True, answer=f"Nuk jam ende super inteligjente 😄 por kuptova: {q}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
