"""
Database Configuration and Connection
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration
# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")

print("--- DEBUG: CONNECTION CONFIG ---")
print(f"DATABASE_URL set: {bool(DATABASE_URL)}")
print(f"PGHOST set: {bool(os.getenv('PGHOST'))}")
print(f"PGUSER set: {bool(os.getenv('PGUSER'))}")
print(f"PGPASSWORD set: {bool(os.getenv('PGPASSWORD'))}")
print(f"PGDATABASE set: {bool(os.getenv('PGDATABASE'))}")
print("--------------------------------")

# If DATABASE_URL is not set, try to construct it from PG* variables
if not DATABASE_URL:
    import urllib.parse
    
    db_host = os.getenv("PGHOST")
    db_user = os.getenv("PGUSER")
    db_pass = os.getenv("PGPASSWORD")
    db_name = os.getenv("PGDATABASE")
    db_port = os.getenv("PGPORT", "5432")

    if db_host and db_user and db_pass and db_name:
        encoded_pass = urllib.parse.quote_plus(db_pass)
        DATABASE_URL = f"postgresql://{db_user}:{encoded_pass}@{db_host}:{db_port}/{db_name}"
    else:
        # Fallback to local development
        DATABASE_URL = "postgresql://pmascc_user:pmascc_pass@localhost:5432/pmascc_db"

# Create engine
engine = create_engine(
    DATABASE_URL,
    echo=True,  # Set to False in production
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,
    max_overflow=20
)

# Create session maker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    Dependency for FastAPI to get database session
    Usage:
        @app.get("/endpoint")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database - create all tables if they don't exist
    """
    from db.models import Base
    Base.metadata.create_all(bind=engine)
    print("✓ Database tables created successfully")


def test_connection():
    """
    Test database connection
    """
    try:
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        print("✓ Database connection successful")
        return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False


if __name__ == "__main__":
    # Test connection
    test_connection()
    
    # Initialize database
    init_db()
