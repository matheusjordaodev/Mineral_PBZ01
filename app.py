from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Import routers
from routes import campanhas, files, auth, dados, cadastros, estacoes, imagens, documentos, export

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Include routers
app.include_router(campanhas.router)
app.include_router(files.router)
app.include_router(auth.router)
app.include_router(dados.router)
app.include_router(cadastros.router)
app.include_router(estacoes.router)
app.include_router(imagens.router)
app.include_router(documentos.router)
app.include_router(export.router)

@app.on_event("startup")
async def startup_event():
    import time
    from db.database import SessionLocal, init_db, engine
    from db.seeds import seed_admin, seed_ilhas, seed_cadastros, seed_espacos_amostrais
    from sqlalchemy.exc import OperationalError

    # Wait for database to be ready (retry up to 5 times)
    retries = 5
    while retries > 0:
        try:
            # Test connection
            with engine.connect() as conn:
                break
        except OperationalError:
            retries -= 1
            print(f"Waiting for database... ({retries} retries left)")
            time.sleep(2)
    
    # Ensure tables are created (especially new ones)
    init_db()
    
    db = SessionLocal()
    try:
        seed_ilhas(db)
        seed_espacos_amostrais(db)
        seed_admin(db)
        seed_cadastros(db)
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    response = templates.TemplateResponse("index.html", {"request": request})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8001, reload=True)
