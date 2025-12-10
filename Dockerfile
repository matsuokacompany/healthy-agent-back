# ---------- STAGE 1: BUILDER ----------
FROM python:3.11-slim AS builder

WORKDIR /app

# Instalar dependências do sistema necessárias para compilar libs como psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia apenas requirements para aproveitar o cache
COPY requirements.txt .

# Instala dependências isoladamente para copiar depois
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ---------- STAGE 2: FINAL ----------
FROM python:3.11-slim

WORKDIR /app

# Copia bibliotecas instaladas do stage "builder"
COPY --from=builder /install /usr/local

# Copia o restante do código
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
