# ── Dockerfile for ML-Enhanced Data Center Digital Twin Platform ──
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

# Install system dependencies (build-essential for numpy/scipy if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy frontend assets and backend code
COPY index.html /app/index.html
COPY style.css /app/style.css
COPY js/ /app/js/
COPY backend/ /app/backend/

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
