from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "LUNA server running ✅  Provo: /ask?q=pershendetje"

@app.route("/ask", methods=["GET"])
def ask():
    q = request.args.get("q", "").strip().lower()

    if not q:
        return jsonify(ok=False, error="mungon parametri q"), 400

    # demo responses
    if "ora" in q:
        answer = "Ora aktuale po vjen nga serveri."
    elif "moti" in q:
        answer = "Moti ne Londer eshte me re."
    elif "luaj" in q:
        answer = "Po e nis muziken qe kerkove."
    else:
        answer = f"Degjova: {q}"

    return jsonify(ok=True, answer=answer)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
