FROM python:3.11-slim

WORKDIR /app

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir -r requirements.txt

CMD gunicorn run:app --bind 0.0.0.0:${PORT:-10000} --workers 2 --timeout 120
