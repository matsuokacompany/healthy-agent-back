from sqlalchemy.orm import declarative_base

# Base usada pelo Alembic e SQLAlchemy
Base = declarative_base()

# Importar modelos para registrar no metadata
from app.models.models import User, Anamnese, Symptom, DailyLog