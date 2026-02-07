FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY server.py /app/server.py

# Railway do të japë PORT vetë. Ne bëjmë fallback 8080.
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}"]
