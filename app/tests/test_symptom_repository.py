import pytest
from app.db.base import SessionLocal, Base, engine
from app.db.repositories.user_repository import UserRepository
from app.db.repositories.symptom_repository import SymptomRepository
from app.models.models import User, Symptom, Anamnese, DailyLog

# Cria tabelas no banco de teste (ou real)
Base.metadata.create_all(bind=engine)

@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        # Limpa dados antes de cada teste
        session.query(DailyLog).delete()
        session.query(Symptom).delete()
        session.query(Anamnese).delete()
        session.query(User).delete()
        session.commit()
        yield session
    finally:
        session.close()

def test_create_and_get_symptom(db):
    # Cria usuário para associar os sintomas
    user_repo = UserRepository(db)
    symptom_repo = SymptomRepository(db)

    user = user_repo.create(name="TestUser", email="testuser@example.com")
    assert user.id is not None

    # Cria sintoma
    symptom = symptom_repo.create(user_id=user.id, description="Dor de cabeça")
    assert symptom.id is not None
    assert symptom.description == "Dor de cabeça"

    # Busca sintomas do usuário
    symptoms = symptom_repo.get_symptoms_by_user(user.id)
    assert len(symptoms) == 1
    assert symptoms[0].description == "Dor de cabeça"
