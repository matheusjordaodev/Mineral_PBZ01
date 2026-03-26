"""
Database Configuration and Connection
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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
        raise RuntimeError(
            "Banco de dados não configurado. "
            "Defina DATABASE_URL ou as variáveis PGHOST, PGUSER, PGPASSWORD, PGDATABASE no arquivo .env"
        )


# Create engine
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,
    max_overflow=20,
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
    Initialize database - create all tables if they do not exist.
    """
    import time as _time

    # CREATE EXTENSION pode falhar com "tuple concurrently updated" quando múltiplos
    # workers fazem startup ao mesmo tempo. Retry com back-off resolve a race condition.
    for attempt in range(3):
        try:
            with engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            break  # sucesso
        except SQLAlchemyError as exc:
            err_str = str(exc).lower()
            if "concurrently updated" in err_str or "duplicate" in err_str:
                # Outro worker já está criando — aguarda e tenta de novo
                _time.sleep(1 + attempt)
                continue
            # PostGIS não está disponível no banco
            raise RuntimeError(
                "PostGIS extension is required. Enable it in the target database "
                "before starting the app (example: CREATE EXTENSION postgis;)."
            ) from exc

    from db.models import Base

    Base.metadata.create_all(bind=engine)

    def _safe_exec(conn, sql: str) -> None:
        """Executa DDL ignorando erros de concorrência (race condition entre workers)."""
        try:
            conn.execute(text(sql))
        except SQLAlchemyError as exc:
            if "concurrently updated" in str(exc).lower() or "already exists" in str(exc).lower():
                pass  # outro worker já executou — ok
            else:
                raise

    # Migration: adiciona data_fim em campanhas (idempotente via IF NOT EXISTS)
    with engine.begin() as conn:
        _safe_exec(conn, """
            ALTER TABLE campanhas
            ADD COLUMN IF NOT EXISTS data_fim DATE;
        """)

    # Migration: adiciona espaco_amostral_id em feicoes_kml (idempotente via IF NOT EXISTS)
    with engine.begin() as conn:
        _safe_exec(conn, """
            ALTER TABLE feicoes_kml
            ADD COLUMN IF NOT EXISTS espaco_amostral_id INTEGER
                REFERENCES espacos_amostrais(id);
        """)
        _safe_exec(conn, """
            CREATE INDEX IF NOT EXISTS ix_feicoes_kml_espaco_amostral_id
                ON feicoes_kml(espaco_amostral_id);
        """)

    # Índice espacial GIST
    with engine.begin() as conn:
        _safe_exec(conn, "CREATE INDEX IF NOT EXISTS ix_feicoes_kml_geom ON feicoes_kml USING GIST(geom);")

    # Performance indexes para FK columns
    with engine.begin() as conn:
        _safe_exec(conn, "CREATE INDEX IF NOT EXISTS ix_estacoes_campanha_id ON estacoes_amostrais(campanha_id);")
        _safe_exec(conn, "CREATE INDEX IF NOT EXISTS ix_estacoes_espaco_id ON estacoes_amostrais(espaco_amostral_id);")
        _safe_exec(conn, "CREATE INDEX IF NOT EXISTS ix_buscas_ativas_estacao_id ON buscas_ativas(estacao_amostral_id);")
        _safe_exec(conn, "CREATE INDEX IF NOT EXISTS ix_fotoquadrados_estacao_id ON fotoquadrados(estacao_amostral_id);")
        _safe_exec(conn, "CREATE INDEX IF NOT EXISTS ix_video_transectos_estacao_id ON video_transectos(estacao_amostral_id);")

    # View usada pelo GeoServer
    with engine.begin() as conn:
        _safe_exec(conn, """
            CREATE OR REPLACE VIEW vw_espacos_amostrais_geo AS
            SELECT
                ea.id,
                ea.ilha_id,
                ea.codigo,
                ea.nome,
                ea.descricao,
                ea.metodologia,
                ea.latitude,
                ea.longitude,
                ST_SetSRID(ST_MakePoint(ea.longitude, ea.latitude), 4326)::geometry(Point, 4326) AS localizacao
            FROM espacos_amostrais ea
            WHERE ea.deleted_at IS NULL
              AND ea.latitude IS NOT NULL
              AND ea.longitude IS NOT NULL
        """)

    print("Database tables and views created successfully")


def test_connection():
    """
    Test database connection
    """
    try:
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        print("Database connection successful")
        return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False


if __name__ == "__main__":
    # Test connection
    test_connection()

    # Initialize database
    init_db()
