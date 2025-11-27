FROM python:3.11-slim

# diretório do app dentro do container
WORKDIR /app

# Copiar apenas requirements para instalar as libs
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo o restante do projeto
COPY . .

# Porta padrão do FastAPI
EXPOSE 8000

# Comando para iniciar a API
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

