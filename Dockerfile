FROM python:3.11-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
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

RUN pip install --no-cache-dir -r requirements.txt

COPY package*.json ./

RUN npm install

RUN npx playwright install --with-deps chromium

COPY . .

RUN mkdir -p logs
RUN mkdir -p data/uploads/temp
RUN mkdir -p tests/performance/gatling/target
RUN mkdir -p playwright-report
RUN mkdir -p test-results

EXPOSE 5000

CMD ["gunicorn", "app:app", "--workers", "3", "--bind", "0.0.0.0:5000", "--timeout", "300"]