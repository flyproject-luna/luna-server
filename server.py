import os
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.get("/")
def home():
    return "Luna server online ✅", 200

@app.get("/health")
def health():
    return jsonify(status="ok"), 200

@app.get("/ask")
def ask():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify(error="missing q", ok=False), 400

    return jsonify(
        answer=f"Luna degjoi: {q}",
        ok=True
    ), 200

@app.post("/alarm/set")
def set_alarm():
    data = request.get_json(silent=True) or {}
    return jsonify(ok=True, alarm=data), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
