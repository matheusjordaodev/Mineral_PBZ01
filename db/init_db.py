"""
Initialize database tables from SQLAlchemy models
Run this script to create all tables defined in db/models.py
"""
from db.database import engine, SessionLocal
from db.models import Base  # Import Base from models, not database
from db.models import *  # Import all models to register them
from db.seeds import seed_admin, seed_ilhas, seed_espacos_amostrais
from db.database import SessionLocal

def init_db():
    """Create all tables and seed initial data"""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✓ Tables created successfully")
    
    print("\nSeeding initial data...")
    db = SessionLocal()
    try:
        seed_ilhas(db)
        print("✓ Ilhas seeded")
        seed_espacos_amostrais(db)
        print("✓ Espaços Amostrais seeded")
        seed_admin(db)
        print("✓ Admin user created")
    finally:
        db.close()
    
    print("\n✅ Database initialization complete!")

if __name__ == "__main__":
    init_db()
