FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# instance/ will be overridden by the Fly volume mount at runtime
RUN mkdir -p instance

EXPOSE 8080

# Single worker keeps APScheduler in one process
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "120", "main:app"]
