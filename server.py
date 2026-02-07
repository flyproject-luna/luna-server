import os
from fastapi import FastAPI

app = FastAPI()

PORT = int(os.environ.get("PORT", 8080))

@app.get("/")
def root():
    return "ok"

@app.get("/health")
def health():
    return {"status": "ok"}
