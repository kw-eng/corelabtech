FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    curl \
    git \
    ca-certificates \
    nodejs \
    npm \
    default-jdk \
    maven \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential gcc \
    && rm -rf /root/.cache/pip

COPY package*.json ./

RUN npm ci \
    && npm cache clean --force

RUN npx playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /tmp/*

COPY . .

RUN mkdir -p \
    logs \
    data/uploads/temp \
    data/performance \
    tests/performance/gatling/target \
    playwright-report \
    test-results

EXPOSE 5000

CMD ["gunicorn", "app:app", "--workers", "3", "--bind", "0.0.0.0:5000", "--timeout", "300"]
