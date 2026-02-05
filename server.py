from flask import Flask, request, jsonify

app = Flask(__name__)

@app.get("/")
def home():
    return "LUNA SERVER OK ✅  /ask?q=pyetja"

@app.get("/ask")
def ask():
    q = request.args.get("q", "").strip()

    if not q:
        return jsonify(ok=False, error="Mungon parametri q"), 400

    # DEMO response (pa AI akoma)
    answer = f"E mora pyetjen: {q}"

    return jsonify(
        ok=True,
        question=q,
        answer=answer
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
