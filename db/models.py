"""
Database Models for PMASCC
SQLAlchemy + GeoAlchemy2 for PostGIS support
Updated to V8 Schema: EstacaoAmostral, Techniques, Documentos, BaseApoio, Embarcacao, Equipe, Soft Deletes, Timestamps.
"""

from sqlalchemy import Column, Integer, String, Text, Date, DateTime, BigInteger, Boolean, ForeignKey, CheckConstraint, Numeric, Interval, Time, Enum, Float
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

class BaseModel(Base):
    """Abstract base model with timestamps and soft delete"""
    __abstract__ = True
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)


class BaseApoio(BaseModel):
    __tablename__ = 'bases_apoio'
    
    id = Column(Integer, primary_key=True)
    nome = Column(String(200), nullable=False)
    localizacao = Column(Geometry('POINT', srid=4326))
    
    campanhas = relationship("Campanha", back_populates="base_apoio")

class Embarcacao(BaseModel):
    __tablename__ = 'embarcacoes'
    
    id = Column(Integer, primary_key=True)
    nome = Column(String(200), nullable=False)
    marinheiro_responsavel = Column(String(200))
    
    campanhas = relationship("Campanha", back_populates="embarcacao")

class MembroEquipe(BaseModel):
    __tablename__ = 'membros_equipe'
    
    id = Column(Integer, primary_key=True)
    nome_completo = Column(String(200), nullable=False)
    funcao = Column(String(100))

    campanhas = relationship("Campanha", secondary="equipes_campanha", back_populates="equipe")


class CampanhaIlha(Base):
    """Tabela associativa Campanha <-> Ilha"""
    __tablename__ = 'campanhas_ilhas'
    
    campanha_id = Column(Integer, ForeignKey('campanhas.id'), primary_key=True)
    ilha_id = Column(Integer, ForeignKey('ilhas.id'), primary_key=True)

class EquipeCampanha(Base):
    """Tabela associativa Campanha <-> MembroEquipe"""
    __tablename__ = 'equipes_campanha'
    
    campanha_id = Column(Integer, ForeignKey('campanhas.id'), primary_key=True)
    membro_equipe_id = Column(Integer, ForeignKey('membros_equipe.id'), primary_key=True)

class EspacoAmostral(BaseModel):
    """Modelo para Pontos/Estações de Amostragem fixos por ilha (e.g., IC01, IA02)"""
    __tablename__ = 'espacos_amostrais'
    
    id = Column(Integer, primary_key=True)
    ilha_id = Column(Integer, ForeignKey('ilhas.id'), nullable=False)
    codigo = Column(String(20))  # e.g., IC01, IA02, IV01
    nome = Column(String(200), nullable=False)
    descricao = Column(Text)
    metodologia = Column(String(50))  # BA, FQ e VT
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    ilha = relationship("Ilha", back_populates="espacos_amostrais")
    estacoes_amostrais = relationship("EstacaoAmostral", back_populates="espaco_amostral")
    feicoes_kml = relationship("FeicaoKml", back_populates="espaco_amostral")

class Ilha(BaseModel):
    """Modelo para tabela de ilhas"""
    __tablename__ = 'ilhas'
    
    id = Column(Integer, primary_key=True)
    codigo = Column(String(50), unique=True, nullable=False, index=True)
    nome = Column(String(200), nullable=False)
    regiao = Column(String(100))
    localizacao = Column(Geometry('POINT', srid=4326))
    descricao = Column(Text)
    
    campanhas = relationship("Campanha", secondary="campanhas_ilhas", back_populates="ilhas")
    espacos_amostrais = relationship("EspacoAmostral", back_populates="ilha", cascade="all, delete-orphan")

class Campanha(BaseModel):
    """Modelo para tabela de campanhas"""
    __tablename__ = 'campanhas'
    
    id = Column(Integer, primary_key=True)
    # ilha_id mantido como nullable para compatibilidade ou ilha principal, mas o relacionamento principal agora é M:N
    ilha_id = Column(Integer, ForeignKey('ilhas.id'), nullable=True, index=True) 
    base_apoio_id = Column(Integer, ForeignKey('bases_apoio.id'))
    embarcacao_id = Column(Integer, ForeignKey('embarcacoes.id'))
    
    codigo = Column(String(100), unique=True, nullable=False)
    nome = Column(String(200), nullable=False)
    data_campanha = Column(Date, nullable=False, index=True)
    data_fim = Column(Date, nullable=True)
    descricao = Column(Text)
    status = Column(String(50), default='ativa', index=True)
    
    # Relationships
    ilhas = relationship("Ilha", secondary="campanhas_ilhas", back_populates="campanhas")
    base_apoio = relationship("BaseApoio", back_populates="campanhas")
    embarcacao = relationship("Embarcacao", back_populates="campanhas")
    equipe = relationship("MembroEquipe", secondary="equipes_campanha", back_populates="campanhas")
    
    estacoes_amostrais = relationship("EstacaoAmostral", back_populates="campanha", cascade="all, delete-orphan")
    documentos = relationship("Documento", back_populates="campanha", cascade="all, delete-orphan")
    feicoes_kml = relationship("FeicaoKml", back_populates="campanha", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.codigo,
            "uuid": self.codigo,
            "db_id": self.id,
            "ilha_ids": [i.id for i in self.ilhas],
            "ilha_nomes": [i.nome for i in self.ilhas],
            "base_apoio_id": self.base_apoio_id,
            "embarcacao_id": self.embarcacao_id,
            "codigo": self.codigo,
            "nome": self.nome,
            "data": self.data_campanha.isoformat() if self.data_campanha else None,
            "data_fim": self.data_fim.isoformat() if self.data_fim else None,
            "descricao": self.descricao,
            "status": self.status
        }

class Documento(BaseModel):
    __tablename__ = 'documentos'

    id = Column(Integer, primary_key=True)
    campanha_id = Column(Integer, ForeignKey('campanhas.id'), nullable=True) # Opcional
    titulo = Column(String(200), nullable=False)
    url = Column(Text, nullable=False)
    data_upload = Column(DateTime, server_default=func.now())
    tipo = Column(String(50)) # especificacao, projeto_exec, rel_parcial, rel_final, rel_campo

    campanha = relationship("Campanha", back_populates="documentos")


class FeicaoKml(BaseModel):
    """Feições geoespaciais importadas de arquivos KML/KMZ, persistidas no PostGIS."""
    __tablename__ = 'feicoes_kml'

    id = Column(Integer, primary_key=True)
    campanha_id = Column(Integer, ForeignKey('campanhas.id'), nullable=False, index=True)
    espaco_amostral_id = Column(Integer, ForeignKey('espacos_amostrais.id'), nullable=True, index=True)
    # ilha_id é derivado de espaco_amostral.ilha_id; mantido para compatibilidade com registros antigos
    ilha_id = Column(Integer, ForeignKey('ilhas.id'), nullable=True, index=True)

    arquivo_origem = Column(String(500))          # nome do arquivo KML
    nome = Column(String(500))                    # nome do placemark
    descricao = Column(Text)                      # descrição do placemark
    tipo_geometria = Column(String(50))           # Point | LineString | Polygon
    geom = Column(Geometry(geometry_type='GEOMETRY', srid=4326))
    propriedades = Column(JSONB, default={})      # quaisquer propriedades extras

    campanha = relationship("Campanha", back_populates="feicoes_kml")
    espaco_amostral = relationship("EspacoAmostral", back_populates="feicoes_kml")
    ilha = relationship("Ilha")

class EstacaoAmostral(BaseModel):
    __tablename__ = 'estacoes_amostrais'
    
    id = Column(Integer, primary_key=True)
    campanha_id = Column(Integer, ForeignKey('campanhas.id'), nullable=False)
    espaco_amostral_id = Column(Integer, ForeignKey('espacos_amostrais.id'), nullable=True) # Link to specific space
    
    numero = Column(Integer) # 1 a 8 (Ponto Amostral dentro do Espaço)
    data = Column(Date)
    hora = Column(Time)
    localizacao = Column(Geometry('POINT', srid=4326))
    observacoes = Column(Text)
    
    campanha = relationship("Campanha", back_populates="estacoes_amostrais")
    espaco_amostral = relationship("EspacoAmostral", back_populates="estacoes_amostrais")
    
    fotoquadrados = relationship("Fotoquadrado", back_populates="estacao_amostral", cascade="all, delete-orphan")
    buscas_ativas = relationship("BuscaAtiva", back_populates="estacao_amostral", cascade="all, delete-orphan")
    video_transectos = relationship("VideoTransecto", back_populates="estacao_amostral", cascade="all, delete-orphan")

class Fotoquadrado(BaseModel):
    __tablename__ = 'fotoquadrados'
    
    id = Column(Integer, primary_key=True)
    estacao_amostral_id = Column(Integer, ForeignKey('estacoes_amostrais.id'), nullable=False)
    
    data = Column(Date)
    hora = Column(Time)
    localizacao = Column(Geometry('POINT', srid=4326))
    profundidade = Column(Numeric(5,2))
    temperatura = Column(Numeric(4,2))
    visibilidade_vertical = Column(Numeric(5,2))
    visibilidade_horizontal = Column(Numeric(5,2))
    
    imagem_mosaico_url = Column(Text)
    imagens_complementares = Column(JSONB) # List of URLs (max 20)
    dados_meteo = Column(JSONB)
    
    riqueza_especifica = Column(Numeric(10,4))
    diversidade_shannon = Column(Numeric(10,4))
    equitabilidade_jaccard = Column(Numeric(10,4))
    
    estacao_amostral = relationship("EstacaoAmostral", back_populates="fotoquadrados")

class BuscaAtiva(BaseModel):
    __tablename__ = 'buscas_ativas'
    
    id = Column(Integer, primary_key=True)
    estacao_amostral_id = Column(Integer, ForeignKey('estacoes_amostrais.id'), nullable=False)
    
    numero_busca = Column(Integer) # 1 a 6
    data = Column(Date)
    hora_inicio = Column(Time)
    duracao = Column(Interval)
    trilha = Column(Geometry('LINESTRING', srid=4326))
    
    profundidade_inicial = Column(Numeric(8,2))
    profundidade_final = Column(Numeric(8,2))
    temperatura_inicial = Column(Numeric(8,2))
    temperatura_final = Column(Numeric(8,2))
    visibilidade_vertical = Column(Numeric(8,2))
    visibilidade_horizontal = Column(Numeric(8,2))
    
    planilha_excel_url = Column(Text)
    arquivo_percurso_url = Column(Text)
    dados_meteo = Column(JSONB)
    imagens = Column(JSONB) # Max 5
    
    encontrou_coral_sol = Column(Boolean, default=False)
    
    estacao_amostral = relationship("EstacaoAmostral", back_populates="buscas_ativas")
    protocolos_dafor = relationship("ProtocoloDAFOR", back_populates="busca_ativa", cascade="all, delete-orphan")

class ProtocoloDAFOR(BaseModel):
    __tablename__ = 'protocolos_dafor'
    
    id = Column(Integer, primary_key=True)
    busca_ativa_id = Column(Integer, ForeignKey('buscas_ativas.id'), nullable=False)
    
    data = Column(Date)
    hora = Column(Time)
    
    temperatura_inicial = Column(Numeric(4,2))
    temperatura_final = Column(Numeric(4,2))
    profundidade_inicial = Column(Numeric(5,2))
    profundidade_final = Column(Numeric(5,2))
    iar = Column(Numeric(10,4))
    
    imagens = Column(JSONB) # Max 5
    abundancia = Column(String(50)) # D, A, F, O, R
    detalhes = Column(JSONB)
    
    busca_ativa = relationship("BuscaAtiva", back_populates="protocolos_dafor")

class VideoTransecto(BaseModel):
    __tablename__ = 'video_transectos'
    
    id = Column(Integer, primary_key=True)
    estacao_amostral_id = Column(Integer, ForeignKey('estacoes_amostrais.id'), nullable=False)
    
    data = Column(Date)
    hora = Column(Time)
    trilha = Column(Geometry('LINESTRING', srid=4326))
    
    profundidade_inicial = Column(Numeric(5,2))
    profundidade_final = Column(Numeric(5,2))
    temperatura_inicial = Column(Numeric(4,2))
    temperatura_final = Column(Numeric(4,2))
    visibilidade_horizontal = Column(Numeric(5,2))
    visibilidade_vertical = Column(Numeric(5,2))
    
    video_url = Column(Text)
    dados_meteo = Column(JSONB)
    riqueza_especifica = Column(Numeric(10,4))
    diversidade_shannon = Column(Numeric(10,4))
    equitabilidade_jaccard = Column(Numeric(10,4))
    
    estacao_amostral = relationship("EstacaoAmostral", back_populates="video_transectos")

class Usuario(BaseModel):
    __tablename__ = 'usuarios'
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    nome_completo = Column(String)
    email = Column(String, unique=True, index=True)
    senha_hash = Column(String)
    perfil = Column(Enum('usuario', 'pesquisador', 'admin', name='perfil_usuario'))
    ativo = Column(Boolean, default=True)

