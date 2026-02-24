import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.environ.get("PGHOST"),
    user=os.environ.get("PGUSER"),
    password=os.environ.get("PGPASSWORD"),
    dbname=os.environ.get("PGDATABASE"),
    port=os.environ.get("PGPORT", 5432)
)

cur = conn.cursor()

commands = [
    "ALTER TABLE buscas_ativas ALTER COLUMN profundidade_inicial TYPE numeric(8,2);",
    "ALTER TABLE buscas_ativas ALTER COLUMN profundidade_final TYPE numeric(8,2);",
    "ALTER TABLE buscas_ativas ALTER COLUMN temperatura_inicial TYPE numeric(8,2);",
    "ALTER TABLE buscas_ativas ALTER COLUMN temperatura_final TYPE numeric(8,2);",
    "ALTER TABLE buscas_ativas ALTER COLUMN visibilidade_vertical TYPE numeric(8,2);",
    "ALTER TABLE buscas_ativas ALTER COLUMN visibilidade_horizontal TYPE numeric(8,2);",
    "ALTER TABLE fotoquadrados ALTER COLUMN profundidade TYPE numeric(8,2);",
    "ALTER TABLE fotoquadrados ALTER COLUMN temperatura TYPE numeric(8,2);",
    "ALTER TABLE fotoquadrados ALTER COLUMN visibilidade_vertical TYPE numeric(8,2);",
    "ALTER TABLE fotoquadrados ALTER COLUMN visibilidade_horizontal TYPE numeric(8,2);",
    "ALTER TABLE video_transectos ALTER COLUMN temperatura_inicial TYPE numeric(8,2);",
    "ALTER TABLE video_transectos ALTER COLUMN temperatura_final TYPE numeric(8,2);",
    "ALTER TABLE video_transectos ALTER COLUMN profundidade_inicial TYPE numeric(8,2);",
    "ALTER TABLE video_transectos ALTER COLUMN profundidade_final TYPE numeric(8,2);",
    "ALTER TABLE video_transectos ALTER COLUMN visibilidade_horizontal TYPE numeric(8,2);",
    "ALTER TABLE video_transectos ALTER COLUMN visibilidade_vertical TYPE numeric(8,2);",
    "ALTER TABLE protocolos_dafor ALTER COLUMN temperatura_inicial TYPE numeric(8,2);",
    "ALTER TABLE protocolos_dafor ALTER COLUMN temperatura_final TYPE numeric(8,2);",
    "ALTER TABLE protocolos_dafor ALTER COLUMN profundidade_inicial TYPE numeric(8,2);",
    "ALTER TABLE protocolos_dafor ALTER COLUMN profundidade_final TYPE numeric(8,2);"
]

try:
    for cmd in commands:
        print(f"Executing: {cmd}")
        cur.execute(cmd)
    conn.commit()
    print("Sucesso ao atualizar precisão numérica das tabelas.")
except Exception as e:
    print(f"Erro: {e}")
    conn.rollback()
finally:
    cur.close()
    conn.close()
