from fastapi import FastAPI
from app.bot.whatsapp_bot import app as whatsapp_app

app = FastAPI()

# Incluir as rotas do bot dentro da API principal
app.mount("/", whatsapp_app)
