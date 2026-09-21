FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/golden-jarvis

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system jarvis \
    && adduser --system --ingroup jarvis jarvis
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
COPY deploy ./deploy
COPY .env.production.example ./.env.production.example
RUN chmod +x deploy/*.sh \
    && mkdir -p data uploads/pending uploads/processed logs backups \
    && chown -R jarvis:jarvis /opt/golden-jarvis

USER jarvis
WORKDIR /opt/golden-jarvis/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8780", "--proxy-headers", "--forwarded-allow-ips", "*"]
