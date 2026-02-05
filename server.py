from flask import Flask, request, jsonify

app = Flask(__name__)

@app.get("/")
def home():
    return "LUNA server running ✅  Shko te: /ask?q=pershendetje"

@app.get("/ask")
def ask():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify(ok=False, error="mungon parametri q. shembull: /ask?q=pershendetje"), 400

    # PER MOMENTIN: përgjigje demo (jo AI)
    # Këtu më vonë fusim “AI” / API / lajme / etj.
    answer = f"Pershendetje! Me shkruajte: {q}"
    return jsonify(ok=True, answer=answer)

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
