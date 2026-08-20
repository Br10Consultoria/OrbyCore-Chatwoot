FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN addgroup --system bridge && adduser --system --ingroup bridge bridge
COPY pyproject.toml ./
COPY bridge/app ./app
RUN pip install --no-cache-dir .
USER bridge

EXPOSE 8081
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/ready', timeout=3)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081", "--proxy-headers", "--forwarded-allow-ips", "*"]
