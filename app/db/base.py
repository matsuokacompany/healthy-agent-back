from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine
from app.core.config import settings

Base = declarative_base()
engine = create_engine(settings.DATABASE_URL, echo=True)

# IMPORTANTE: importar todos os models aqui
from app.models.models import User, Anamnese, Symptom, DailyLog
