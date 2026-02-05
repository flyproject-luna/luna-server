from flask import Flask, request, jsonify

app = Flask(__name__)

@app.get("/")
def home():
    return "LUNA server running OK"

@app.get("/esp32")
def esp32():
    q = request.args.get("q", "").strip().lower()

    if not q:
        return jsonify(ok=False, error="missing q"), 400

    # LOGJIKË BAZË (demo)
    if "ora" in q:
        answer = "Ora aktuale është 12:00"
    elif "mot" in q:
        answer = "Moti është me diell"
    elif "luaj" in q:
        answer = "Po hap muzikën në YouTube"
    else:
        answer = f"Nuk e kuptova: {q}"

    return jsonify(ok=True, answer=answer)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
