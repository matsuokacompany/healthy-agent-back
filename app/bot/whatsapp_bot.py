# app/bot/whatsapp_bot.py
import os
import requests
from fastapi import FastAPI, Request
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone

from app.db.session import engine
from app.db.repositories.user_repository import UserRepository
from app.db.repositories.symptom_repository import SymptomRepository
from app.db.repositories.daily_log_repository import DailyLogRepository
from app.services.report_service import ReportService

app = FastAPI()

# Configurações
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_ID")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
SessionLocal = sessionmaker(bind=engine)

# ==========================
# 🔹 VERIFICAÇÃO WEBHOOK
# ==========================
@app.get("/webhook")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return int(challenge)
    return {"error": "Invalid token"}, 403

# ==========================
# 🔹 RECEBIMENTO DE MENSAGENS
# ==========================
@app.post("/webhook")
async def receive_message(request: Request):
    data = await request.json()
    try:
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]
        user_number = message["from"]
        text = message["text"]["body"].strip().lower()

        db = SessionLocal()
        user_repo = UserRepository(db)
        symptom_repo = SymptomRepository(db)
        log_repo = DailyLogRepository(db)

        # Cria ou busca usuário
        user = user_repo.get_or_create_by_telegram_id(user_number, f"Usuário {user_number}")

        reply = process_user_message(user, text, db, symptom_repo, log_repo)
        send_whatsapp_message(user_number, reply)
        db.close()
    except Exception as e:
        print("Erro ao processar mensagem:", e)
    return {"status": "received"}

# ==========================
# 🔹 LÓGICA DE INTERAÇÃO
# ==========================
def process_user_message(user, text, db, symptom_repo, log_repo):
    if "não" in text or "nao" in text:
        return "Beleza, sem sintomas registrados hoje 👍"
    
    # Verifica se o texto é um comando de relatório (não obrigatório se agendado)
    if "relatorio semanal" in text:
        return ReportService(db).gerar_relatorio(user.id, "semanal")
    elif "relatorio mensal" in text:
        return ReportService(db).gerar_relatorio(user.id, "mensal")
    
    # Senão, registra sintoma ou atividade
    symptom_repo.create(user.id, text)
    return "Sintoma registrado! Deseja registrar alguma atividade?"

# ==========================
# 🔹 FUNÇÃO DE ENVIO
# ==========================
def send_whatsapp_message(phone_number, message):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": message},
    }
    requests.post(url, headers=headers, json=payload)

# ==========================
# 🔹 AGENDAMENTO AUTOMÁTICO DE RELATÓRIOS
# ==========================
def schedule_reports():
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_weekly_reports, 'cron', day_of_week='mon', hour=8, minute=0)
    scheduler.add_job(send_monthly_reports, 'cron', day=1, hour=8, minute=0)
    scheduler.start()

def send_weekly_reports():
    db = SessionLocal()
    users = UserRepository(db).get_all_users()
    service = ReportService(db)
    for user in users:
        if user.telegram_id:  # pode usar whatsapp_id depois
            msg = service.gerar_relatorio(user.id, "semanal")
            send_whatsapp_message(user.telegram_id, msg)
    db.close()

def send_monthly_reports():
    db = SessionLocal()
    users = UserRepository(db).get_all_users()
    service = ReportService(db)
    for user in users:
        if user.telegram_id:
            msg = service.gerar_relatorio(user.id, "mensal")
            send_whatsapp_message(user.telegram_id, msg)
    db.close()
