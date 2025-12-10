# app/db/base.py
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# IMPORTANTE: importar modelos aqui para registrar no metadata
from app.models.models import User, Anamnese, Symptom, DailyLog
