from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from db.database import get_db
from db.models import BaseApoio, Embarcacao, MembroEquipe, EspacoAmostral

router = APIRouter(prefix="/api", tags=["cadastros"])

# --- Schemas ---
class BaseApoioCreate(BaseModel):
    nome: str
    lat: Optional[float] = None
    lon: Optional[float] = None

class EmbarcacaoCreate(BaseModel):
    nome: str
    marinheiro_responsavel: Optional[str] = None

class MembroCreate(BaseModel):
    nome_completo: str
    funcao: Optional[str] = None

class EspacoAmostralCreate(BaseModel):
    ilha_id: int
    codigo: str
    nome: str
    descricao: Optional[str] = None
    metodologia: str  # "BA" or "FQ e VT"
    latitude: Optional[float] = None
    longitude: Optional[float] = None

# --- Base Apoio ---
@router.get("/bases-apoio")
async def get_bases(db: Session = Depends(get_db)):
    return db.query(BaseApoio).filter(BaseApoio.deleted_at == None).all()

@router.post("/bases-apoio")
async def create_base(base: BaseApoioCreate, db: Session = Depends(get_db)):
    # TODO: Handle Point geometry if lat/lon provided
    new_base = BaseApoio(nome=base.nome)
    if base.lat and base.lon:
        from geoalchemy2.elements import WKTElement
        new_base.localizacao = WKTElement(f"POINT({base.lon} {base.lat})", srid=4326)
    
    db.add(new_base)
    db.commit()
    db.refresh(new_base)
    return new_base

# --- Embarcacoes ---
@router.get("/embarcacoes")
async def get_embarcacoes(db: Session = Depends(get_db)):
    return db.query(Embarcacao).filter(Embarcacao.deleted_at == None).all()

@router.post("/embarcacoes")
async def create_embarcacao(item: EmbarcacaoCreate, db: Session = Depends(get_db)):
    new_item = Embarcacao(nome=item.nome, marinheiro_responsavel=item.marinheiro_responsavel)
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item

# --- Equipe ---
@router.get("/equipe")
async def get_equipe(db: Session = Depends(get_db)):
    return db.query(MembroEquipe).filter(MembroEquipe.deleted_at == None).all()

@router.post("/equipe")
async def create_membro(item: MembroCreate, db: Session = Depends(get_db)):
    new_item = MembroEquipe(nome_completo=item.nome_completo, funcao=item.funcao)
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item

# --- Updates ---

@router.put("/bases-apoio/{id}")
async def update_base(id: int, base: BaseApoioCreate, db: Session = Depends(get_db)):
    item = db.query(BaseApoio).filter(BaseApoio.id == id).first()
    if not item: raise HTTPException(status_code=404)
    item.nome = base.nome
    if base.lat and base.lon:
        from geoalchemy2.elements import WKTElement
        item.localizacao = WKTElement(f"POINT({base.lon} {base.lat})", srid=4326)
    db.commit()
    return item

@router.put("/embarcacoes/{id}")
async def update_embarcacao(id: int, item_data: EmbarcacaoCreate, db: Session = Depends(get_db)):
    item = db.query(Embarcacao).filter(Embarcacao.id == id).first()
    if not item: raise HTTPException(status_code=404)
    item.nome = item_data.nome
    item.marinheiro_responsavel = item_data.marinheiro_responsavel
    db.commit()
    return item

@router.put("/equipe/{id}")
async def update_membro(id: int, item_data: MembroCreate, db: Session = Depends(get_db)):
    item = db.query(MembroEquipe).filter(MembroEquipe.id == id).first()
    if not item: raise HTTPException(status_code=404)
    item.nome_completo = item_data.nome_completo
    item.funcao = item_data.funcao
    db.commit()
    return item

# --- Deletion (Soft Delete) ---
@router.delete("/bases-apoio/{id}")
async def delete_base(id: int, db: Session = Depends(get_db)):
    from datetime import datetime
    item = db.query(BaseApoio).filter(BaseApoio.id == id).first()
    if not item: raise HTTPException(status_code=404)
    item.deleted_at = datetime.now()
    db.commit()
    return {"success": True}

@router.delete("/embarcacoes/{id}")
async def delete_embarcacao(id: int, db: Session = Depends(get_db)):
    from datetime import datetime
    item = db.query(Embarcacao).filter(Embarcacao.id == id).first()
    if not item: raise HTTPException(status_code=404)
    item.deleted_at = datetime.now()
    db.commit()
    return {"success": True}

@router.delete("/equipe/{id}")
async def delete_membro(id: int, db: Session = Depends(get_db)):
    from datetime import datetime
    item = db.query(MembroEquipe).filter(MembroEquipe.id == id).first()
    if not item: raise HTTPException(status_code=404)
    item.deleted_at = datetime.now()
    db.commit()
    return {"success": True}

# --- Estações (Espaços Amostrais) ---
@router.get("/espacos-amostrais")
async def get_espacos_amostrais(ilha_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(EspacoAmostral).filter(EspacoAmostral.deleted_at == None)
    if ilha_id:
        query = query.filter(EspacoAmostral.ilha_id == ilha_id)
    items = query.order_by(EspacoAmostral.codigo).all()
    return [{
        "id": ea.id,
        "ilha_id": ea.ilha_id,
        "codigo": ea.codigo,
        "nome": ea.nome,
        "descricao": ea.descricao,
        "metodologia": ea.metodologia,
        "latitude": ea.latitude,
        "longitude": ea.longitude
    } for ea in items]

@router.post("/espacos-amostrais")
async def create_espaco_amostral(item: EspacoAmostralCreate, db: Session = Depends(get_db)):
    new_item = EspacoAmostral(
        ilha_id=item.ilha_id,
        codigo=item.codigo,
        nome=item.nome,
        descricao=item.descricao,
        metodologia=item.metodologia,
        latitude=item.latitude,
        longitude=item.longitude
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return {"id": new_item.id, "codigo": new_item.codigo, "nome": new_item.nome}

@router.put("/espacos-amostrais/{id}")
async def update_espaco_amostral(id: int, item_data: EspacoAmostralCreate, db: Session = Depends(get_db)):
    item = db.query(EspacoAmostral).filter(EspacoAmostral.id == id).first()
    if not item: raise HTTPException(status_code=404)
    item.codigo = item_data.codigo
    item.nome = item_data.nome
    item.descricao = item_data.descricao
    item.metodologia = item_data.metodologia
    item.latitude = item_data.latitude
    item.longitude = item_data.longitude
    db.commit()
    return {"id": item.id, "codigo": item.codigo, "nome": item.nome}

@router.delete("/espacos-amostrais/{id}")
async def delete_espaco_amostral(id: int, db: Session = Depends(get_db)):
    from datetime import datetime
    item = db.query(EspacoAmostral).filter(EspacoAmostral.id == id).first()
    if not item: raise HTTPException(status_code=404)
    item.deleted_at = datetime.now()
    db.commit()
    return {"success": True}
