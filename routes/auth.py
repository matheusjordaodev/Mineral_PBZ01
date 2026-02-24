from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import timedelta
from datetime import datetime
from typing import List, Optional

from db.database import get_db
from db.models import Usuario
from services.auth_service import verify_password, get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

# Pydantic models (defining here for simplicity/speed, ideally move to separate schemas file)
from pydantic import BaseModel

class Token(BaseModel):
    access_token: str
    token_type: str

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    nome_completo: Optional[str] = None
    perfil: str = "usuario"

class UserUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    nome_completo: Optional[str] = None
    perfil: Optional[str] = None
    ativo: Optional[bool] = None

class UserOut(BaseModel):
    id: int
    username: str
    email: str
    nome_completo: Optional[str]
    perfil: str
    ativo: bool
    
    class Config:
        from_attributes = True

router = APIRouter(tags=["Auth"])

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    from services.auth_service import decode_access_token
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    user = db.query(Usuario).filter(
        Usuario.username == username,
        Usuario.deleted_at == None
    ).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def get_current_active_user(current_user: Usuario = Depends(get_current_user)):
    if not current_user.ativo:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_admin_user(current_user: Usuario = Depends(get_current_active_user)):
    if current_user.perfil != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user

@router.post("/api/login", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(Usuario).filter(
        Usuario.username == form_data.username,
        Usuario.deleted_at == None
    ).first()
    if not user or not verify_password(form_data.password, user.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "perfil": user.perfil},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/api/users/me", response_model=UserOut)
async def read_users_me(current_user: Usuario = Depends(get_current_active_user)):
    return current_user

# CRUD Operations (Admin only)

@router.get("/api/users", response_model=List[UserOut])
async def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: Usuario = Depends(get_admin_user)):
    users = db.query(Usuario)\
        .filter(Usuario.deleted_at == None)\
        .offset(skip)\
        .limit(limit)\
        .all()
    return users

@router.post("/api/users", response_model=UserOut)
async def create_user(user: UserCreate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_admin_user)):
    db_user = db.query(Usuario).filter(
        Usuario.username == user.username,
        Usuario.deleted_at == None
    ).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = get_password_hash(user.password)
    new_user = Usuario(
        username=user.username,
        email=user.email,
        senha_hash=hashed_password,
        nome_completo=user.nome_completo,
        perfil=user.perfil
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.put("/api/users/{user_id}", response_model=UserOut)
async def update_user(user_id: int, user_update: UserUpdate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_admin_user)):
    db_user = db.query(Usuario).filter(
        Usuario.id == user_id,
        Usuario.deleted_at == None
    ).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user_update.password:
        db_user.senha_hash = get_password_hash(user_update.password)
    if user_update.email:
        db_user.email = user_update.email
    if user_update.nome_completo:
        db_user.nome_completo = user_update.nome_completo
    if user_update.perfil:
        db_user.perfil = user_update.perfil
    if user_update.ativo is not None:
        db_user.ativo = user_update.ativo
        
    db.commit()
    db.refresh(db_user)
    return db_user

@router.patch("/api/users/{user_id}/deactivate", response_model=UserOut)
async def deactivate_user(user_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(get_admin_user)):
    db_user = db.query(Usuario).filter(
        Usuario.id == user_id,
        Usuario.deleted_at == None
    ).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    if db_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Admin cannot deactivate own account")

    db_user.ativo = False
    db.commit()
    db.refresh(db_user)
    return db_user

@router.patch("/api/users/{user_id}/activate", response_model=UserOut)
async def activate_user(user_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(get_admin_user)):
    db_user = db.query(Usuario).filter(
        Usuario.id == user_id,
        Usuario.deleted_at == None
    ).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    db_user.ativo = True
    db.commit()
    db.refresh(db_user)
    return db_user

@router.delete("/api/users/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(get_admin_user)):
    db_user = db.query(Usuario).filter(
        Usuario.id == user_id,
        Usuario.deleted_at == None
    ).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    if db_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Admin cannot delete own account")

    # Logical delete only
    db_user.deleted_at = datetime.utcnow()
    db_user.ativo = False
    db.commit()
    return {"message": "User logically deleted"}

# Init Admin User Endpoint (Development/Setup helper)
@router.post("/api/setup/admin")
async def create_initial_admin(db: Session = Depends(get_db)):
    from db.seeds import seed_admin
    seed_admin(db)
    return {"message": "Admin user check/create completed (admin/admin)"}
