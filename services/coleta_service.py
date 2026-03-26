from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

from db.models import (
    BuscaAtiva,
    Campanha,
    EspacoAmostral,
    EstacaoAmostral,
    Fotoquadrado,
    ProtocoloDAFOR,
    VideoTransecto,
)


def to_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if not value:
        return None
    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


def resolve_campanha_reference(campanha_ref: Any, db: Session) -> Optional[Campanha]:
    ref = str(campanha_ref or "").strip()
    if not ref:
        return None

    query = db.query(Campanha).filter(Campanha.deleted_at.is_(None))
    campanha = query.filter(Campanha.codigo == ref).first()
    if campanha:
        return campanha

    try:
        campanha_id = int(ref)
    except (TypeError, ValueError):
        return None

    return query.filter(Campanha.id == campanha_id).first()


def ensure_campanha_exists(campanha_ref: Any, db: Session) -> Campanha:
    campanha = resolve_campanha_reference(campanha_ref, db)
    if not campanha:
        raise HTTPException(status_code=404, detail="Campanha nao encontrada")
    return campanha


def get_or_create_estacao(
    campanha: Campanha,
    espaco_amostral_id: int,
    db: Session,
) -> EstacaoAmostral:
    """Retorna a EstacaoAmostral existente para o par (campanha, espaco_amostral)
    ou cria uma nova automaticamente se ainda não existir."""
    espaco = db.query(EspacoAmostral).filter(EspacoAmostral.id == espaco_amostral_id).first()
    if not espaco:
        raise HTTPException(status_code=404, detail="Espaço amostral não encontrado.")

    estacao = (
        db.query(EstacaoAmostral)
        .filter(
            EstacaoAmostral.campanha_id == campanha.id,
            EstacaoAmostral.espaco_amostral_id == espaco_amostral_id,
            EstacaoAmostral.deleted_at.is_(None),
        )
        .first()
    )

    if not estacao:
        estacao = EstacaoAmostral(
            campanha_id=campanha.id,
            espaco_amostral_id=espaco_amostral_id,
        )
        db.add(estacao)
        db.flush()

    return estacao


def resolve_estacao_for_campanha(
    campanha_ref: Any,
    db: Session,
    estacao_amostral_id: Optional[int] = None,
    espaco_amostral_id: Optional[int] = None,
) -> Tuple[Campanha, EstacaoAmostral]:
    campanha = ensure_campanha_exists(campanha_ref, db)
    campanha_id = campanha.id

    # Novo fluxo: recebeu espaco_amostral_id — cria EstacaoAmostral se não existir
    if espaco_amostral_id is not None:
        estacao = get_or_create_estacao(campanha, espaco_amostral_id, db)
        return campanha, estacao

    # Fluxo legado: recebeu estacao_amostral_id diretamente
    query = (
        db.query(EstacaoAmostral)
        .filter(
            EstacaoAmostral.campanha_id == campanha_id,
            EstacaoAmostral.deleted_at.is_(None),
        )
        .order_by(EstacaoAmostral.id.asc())
    )

    if estacao_amostral_id is None:
        estacoes = query.all()
        if len(estacoes) == 1:
            return campanha, estacoes[0]
        raise HTTPException(
            status_code=400,
            detail="Informe estacao_amostral_id ou espaco_amostral_id.",
        )

    estacao = query.filter(EstacaoAmostral.id == estacao_amostral_id).first()
    if not estacao:
        raise HTTPException(
            status_code=404,
            detail="Estacao amostral nao encontrada para a campanha informada.",
        )
    return campanha, estacao


def _get_next_busca_number(db: Session, estacao_amostral_id: int) -> int:
    items = (
        db.query(BuscaAtiva.numero_busca)
        .filter(
            BuscaAtiva.estacao_amostral_id == estacao_amostral_id,
            BuscaAtiva.deleted_at.is_(None),
        )
        .all()
    )
    numbers = [int(item[0]) for item in items if item[0] is not None]
    return (max(numbers) if numbers else 0) + 1


def _normalize_url_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def create_busca_ativa(
    db: Session,
    campanha_id: int,
    payload: Dict[str, Any],
) -> BuscaAtiva:
    _, estacao = resolve_estacao_for_campanha(
        campanha_id, db,
        estacao_amostral_id=payload.get("estacao_amostral_id"),
        espaco_amostral_id=payload.get("espaco_amostral_id"),
    )

    inicio = normalize_datetime(payload.get("data_hora_inicio"))
    fim = normalize_datetime(payload.get("data_hora_fim"))

    duration = None
    if inicio and fim:
        try:
            duration = fim - inicio
        except Exception:
            duration = None

    data_reg = inicio.date() if inicio else datetime.now().date()
    hora_reg = inicio.time() if inicio else None

    requested_number = payload.get("numero_busca")
    if requested_number in (None, ""):
        numero_busca = _get_next_busca_number(db, estacao.id)
    else:
        try:
            numero_busca = int(requested_number)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="numero_busca invalido") from exc
        if numero_busca <= 0:
            raise HTTPException(status_code=400, detail="numero_busca deve ser maior que zero")
        duplicate = (
            db.query(BuscaAtiva.id)
            .filter(
                BuscaAtiva.estacao_amostral_id == estacao.id,
                BuscaAtiva.numero_busca == numero_busca,
                BuscaAtiva.deleted_at.is_(None),
            )
            .first()
        )
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="Ja existe uma Busca Ativa com esse numero na estacao selecionada.",
            )

    dados_meteo: Dict[str, Any] = {}
    if payload.get("observacoes"):
        dados_meteo["observacoes"] = payload["observacoes"]
    if payload.get("latitude") is not None:
        dados_meteo["lat"] = payload["latitude"]
    if payload.get("longitude") is not None:
        dados_meteo["lon"] = payload["longitude"]
    if isinstance(payload.get("dados_meteo"), dict):
        dados_meteo.update(payload["dados_meteo"])

    db_item = BuscaAtiva(
        estacao_amostral_id=estacao.id,
        numero_busca=numero_busca,
        data=data_reg,
        hora_inicio=hora_reg,
        duracao=duration,
        profundidade_inicial=payload.get("profundidade_inicial"),
        profundidade_final=payload.get("profundidade_final"),
        temperatura_inicial=payload.get("temperatura_inicial"),
        temperatura_final=payload.get("temperatura_final"),
        visibilidade_vertical=payload.get("visibilidade_vertical"),
        visibilidade_horizontal=payload.get("visibilidade_horizontal"),
        encontrou_coral_sol=bool(payload.get("encontrou_coral_sol")),
        imagens=_normalize_url_list(payload.get("imagens")),
        planilha_excel_url=payload.get("planilha_excel_url"),
        arquivo_percurso_url=payload.get("arquivo_percurso_url"),
        dados_meteo=dados_meteo or None,
    )
    db.add(db_item)
    db.flush()

    detalhes_coral = payload.get("detalhes_coral")
    if payload.get("encontrou_coral_sol") and isinstance(detalhes_coral, dict):
        details = dict(detalhes_coral)
        try:
            data_dafor = (
                datetime.strptime(details.get("data"), "%Y-%m-%d").date()
                if details.get("data")
                else data_reg
            )
            hora_dafor = (
                datetime.strptime(details.get("hora"), "%H:%M").time()
                if details.get("hora")
                else hora_reg
            )
        except Exception:
            data_dafor = data_reg
            hora_dafor = hora_reg

        dafor = ProtocoloDAFOR(
            busca_ativa_id=db_item.id,
            data=data_dafor,
            hora=hora_dafor,
            temperatura_inicial=to_float(details.get("temp_inicial")),
            temperatura_final=to_float(details.get("temp_final")),
            profundidade_inicial=to_float(details.get("prof_inicial")),
            profundidade_final=to_float(details.get("prof_final")),
            iar=to_float(details.get("iar")),
            imagens=_normalize_url_list(details.get("imagens")),
            abundancia=details.get("abundancia"),
            detalhes=details,
        )
        db.add(dafor)
        db.flush()

    return db_item


def create_video_transecto(
    db: Session,
    campanha_id: int,
    payload: Dict[str, Any],
) -> VideoTransecto:
    _, estacao = resolve_estacao_for_campanha(
        campanha_id, db,
        estacao_amostral_id=payload.get("estacao_amostral_id"),
        espaco_amostral_id=payload.get("espaco_amostral_id"),
    )

    data_hora = normalize_datetime(payload.get("data_hora"))
    data_reg = data_hora.date() if data_hora else datetime.now().date()
    hora_reg = data_hora.time() if data_hora else None

    video_url = payload.get("video_url")
    observacoes = payload.get("observacoes")
    if not video_url and observacoes and "Video URL:" in observacoes:
        maybe_url = observacoes.split("Video URL:", 1)[1].strip()
        video_url = None if maybe_url.upper() == "N/A" else maybe_url

    dados_meteo: Dict[str, Any] = {}
    if isinstance(payload.get("dados_meteo"), dict):
        dados_meteo.update(payload["dados_meteo"])
    if payload.get("arquivo_percurso_url"):
        dados_meteo.setdefault("arquivo_percurso_url", payload["arquivo_percurso_url"])
    if payload.get("transecto_kml_url"):
        dados_meteo.setdefault("transecto_kml_url", payload["transecto_kml_url"])
    if payload.get("nome_video"):
        dados_meteo.setdefault("nome_video", payload["nome_video"])
    if observacoes:
        dados_meteo.setdefault("observacoes", observacoes)

    db_item = VideoTransecto(
        estacao_amostral_id=estacao.id,
        data=data_reg,
        hora=hora_reg,
        profundidade_inicial=payload.get("profundidade_inicial"),
        profundidade_final=payload.get("profundidade_final"),
        temperatura_inicial=payload.get("temperatura_inicial"),
        temperatura_final=payload.get("temperatura_final"),
        visibilidade_vertical=payload.get("visibilidade_vertical"),
        visibilidade_horizontal=payload.get("visibilidade_horizontal"),
        video_url=video_url,
        dados_meteo=dados_meteo or None,
        riqueza_especifica=payload.get("riqueza_especifica"),
        diversidade_shannon=payload.get("diversidade_shannon"),
        equitabilidade_jaccard=payload.get("equitabilidade_jaccard"),
    )
    db.add(db_item)
    db.flush()
    return db_item


def create_fotoquadrado(
    db: Session,
    campanha_id: int,
    payload: Dict[str, Any],
) -> Fotoquadrado:
    _, estacao = resolve_estacao_for_campanha(
        campanha_id, db,
        estacao_amostral_id=payload.get("estacao_amostral_id"),
        espaco_amostral_id=payload.get("espaco_amostral_id"),
    )

    data_hora = normalize_datetime(payload.get("data_hora"))
    data_reg = data_hora.date() if data_hora else payload.get("data") or datetime.now().date()
    hora_reg = data_hora.time() if data_hora else payload.get("hora")

    dados_meteo: Dict[str, Any] = {}
    if isinstance(payload.get("dados_meteo"), dict):
        dados_meteo.update(payload["dados_meteo"])
    if payload.get("arquivo_percurso_url"):
        dados_meteo.setdefault("arquivo_percurso_url", payload["arquivo_percurso_url"])
    if payload.get("observacoes"):
        dados_meteo.setdefault("observacoes", payload["observacoes"])

    db_item = Fotoquadrado(
        estacao_amostral_id=estacao.id,
        data=data_reg,
        hora=hora_reg,
        profundidade=payload.get("profundidade"),
        temperatura=payload.get("temperatura"),
        visibilidade_vertical=payload.get("visibilidade_vertical"),
        visibilidade_horizontal=payload.get("visibilidade_horizontal"),
        imagem_mosaico_url=payload.get("imagem_mosaico_url"),
        imagens_complementares=_normalize_url_list(payload.get("imagens_complementares")),
        dados_meteo=dados_meteo or None,
        riqueza_especifica=payload.get("riqueza_especifica"),
        diversidade_shannon=payload.get("diversidade_shannon"),
        equitabilidade_jaccard=payload.get("equitabilidade_jaccard"),
    )

    latitude = to_float(payload.get("latitude"))
    longitude = to_float(payload.get("longitude"))
    if latitude is not None and longitude is not None:
        db_item.localizacao = WKTElement(f"POINT({longitude} {latitude})", srid=4326)

    db.add(db_item)
    db.flush()
    return db_item
