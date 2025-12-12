from app.db.base_class import Base

# importa APENAS para registrar no metadata
from app.models.models import User, Anamnese, Symptom, DailyLog

__all__ = ["Base", "User", "Anamnese", "Symptom", "DailyLog"]
