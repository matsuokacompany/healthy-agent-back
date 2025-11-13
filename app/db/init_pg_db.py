from app.db.base import Base, engine
# IMPORTAR TODOS OS MODELOS para garantir que eles sejam registrados
from app.models import models

def init_db():
    print("Criando tabelas no PostgreSQL...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tabelas criadas com sucesso!")

if __name__ == "__main__":
    init_db()
