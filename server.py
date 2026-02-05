from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def root():
    return "LUNA OK"

@app.route("/ask")
def ask():
    q = request.args.get("q", "")
    return jsonify(ok=True, answer=f"Luna degjoi: {q}")

# KJO PJESË ËSHTË KRITIKE
if __name__ != "__main__":
    application = app
