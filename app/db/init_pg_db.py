# app/db/init_db.py
from app.db.session import engine
from app.db.base import Base

def init_db():
    print("Criando tabelas no PostgreSQL via Base.metadata.create_all()...")
    Base.metadata.create_all(bind=engine)
    print("Tabelas criadas!")
