"""
Testes unitários de services/coleta_service.py

Cobre:
  - to_float: conversão de tipos
  - normalize_datetime: normalização de timezone
  - _normalize_url_list: lista de URLs
  - _get_next_busca_number: auto-incremento
  - resolve_campanha_reference: busca por código e por ID
  - get_or_create_estacao: cria nova / reutiliza existente / 404 em espaco inválido
  - resolve_estacao_for_campanha: fluxo novo (espaco_amostral_id) e legado

Todos os testes usam mocks — não requerem PostgreSQL.

Uso:
    python -m pytest tests/test_coleta_service.py -v
    python tests/test_coleta_service.py
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException

from services.coleta_service import (
    to_float,
    normalize_datetime,
    _normalize_url_list,
    _get_next_busca_number,
    resolve_campanha_reference,
    get_or_create_estacao,
    resolve_estacao_for_campanha,
)
from db.models import BuscaAtiva, Campanha, EspacoAmostral, EstacaoAmostral


# ─── helpers ──────────────────────────────────────────────────────────────────

def make_campanha(id: int = 1, codigo: str = "MASC-01") -> MagicMock:
    """MagicMock simples — evita conflito com o mapeamento ORM do SQLAlchemy."""
    c = MagicMock()
    c.id = id
    c.codigo = codigo
    c.deleted_at = None
    return c


def make_espaco(id: int = 10) -> MagicMock:
    e = MagicMock()
    e.id = id
    e.deleted_at = None
    return e


def make_estacao(id: int = 100, campanha_id: int = 1, espaco_amostral_id: int = 10) -> MagicMock:
    est = MagicMock()
    est.id = id
    est.campanha_id = campanha_id
    est.espaco_amostral_id = espaco_amostral_id
    est.deleted_at = None
    return est


def fluent_query(final_result=None, all_result=None):
    """
    Retorna um mock de db.query() com cadeia fluente infinita:
    qualquer .filter().filter().filter()... retorna o mesmo mock.
    O .first() retorna final_result; o .all() retorna all_result.
    """
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.first.return_value = final_result
    q.all.return_value = all_result if all_result is not None else []
    return q


# ─── to_float ─────────────────────────────────────────────────────────────────

class TestToFloat(unittest.TestCase):

    def test_none_retorna_none(self):
        self.assertIsNone(to_float(None))

    def test_string_vazia_retorna_none(self):
        self.assertIsNone(to_float(""))

    def test_inteiro_vira_float(self):
        self.assertEqual(to_float(5), 5.0)
        self.assertIsInstance(to_float(5), float)

    def test_string_numerica(self):
        self.assertAlmostEqual(to_float("3.14"), 3.14)

    def test_string_invalida_retorna_none(self):
        self.assertIsNone(to_float("abc"))

    def test_lista_retorna_none(self):
        self.assertIsNone(to_float([1, 2]))

    def test_zero_e_valido(self):
        self.assertEqual(to_float(0), 0.0)

    def test_negativo(self):
        self.assertAlmostEqual(to_float("-9.8"), -9.8)


# ─── normalize_datetime ───────────────────────────────────────────────────────

class TestNormalizeDatetime(unittest.TestCase):

    def test_none_retorna_none(self):
        self.assertIsNone(normalize_datetime(None))

    def test_naive_datetime_inalterado(self):
        dt = datetime(2024, 6, 15, 10, 30, 0)
        result = normalize_datetime(dt)
        self.assertEqual(result, dt)
        self.assertIsNone(result.tzinfo)

    def test_aware_datetime_vira_naive(self):
        dt_utc = datetime(2024, 6, 15, 13, 0, 0, tzinfo=timezone.utc)
        result = normalize_datetime(dt_utc)
        self.assertIsNone(result.tzinfo, "Resultado deve ser naive (sem tzinfo)")

    def test_aware_com_offset_positivo(self):
        tz_br = timezone(timedelta(hours=-3))
        dt = datetime(2024, 6, 15, 10, 0, 0, tzinfo=tz_br)
        result = normalize_datetime(dt)
        self.assertIsNone(result.tzinfo)

    def test_none_explicito_retorna_none(self):
        self.assertIsNone(normalize_datetime(None))


# ─── _normalize_url_list ──────────────────────────────────────────────────────

class TestNormalizeUrlList(unittest.TestCase):

    def test_lista_de_strings(self):
        result = _normalize_url_list(["http://a.com", "http://b.com"])
        self.assertEqual(result, ["http://a.com", "http://b.com"])

    def test_string_unica_vira_lista(self):
        result = _normalize_url_list("http://a.com")
        self.assertEqual(result, ["http://a.com"])

    def test_none_retorna_lista_vazia(self):
        self.assertEqual(_normalize_url_list(None), [])

    def test_string_vazia_retorna_lista_vazia(self):
        self.assertEqual(_normalize_url_list(""), [])

    def test_lista_com_strings_vazias_filtradas(self):
        result = _normalize_url_list(["http://a.com", "", "  "])
        self.assertEqual(result, ["http://a.com"])

    def test_itens_sao_stripped(self):
        result = _normalize_url_list(["  http://a.com  "])
        self.assertEqual(result, ["http://a.com"])

    def test_lista_vazia(self):
        self.assertEqual(_normalize_url_list([]), [])


# ─── _get_next_busca_number ───────────────────────────────────────────────────

class TestGetNextBuscaNumber(unittest.TestCase):
    """
    _get_next_busca_number(db, estacao_id) faz:
        db.query(BuscaAtiva.numero_busca).filter(...).all()
    Cadeia: query → filter → all
    """

    def _make_db(self, rows: list) -> MagicMock:
        db = MagicMock()
        q = fluent_query(all_result=rows)
        db.query.return_value = q
        return db

    def test_sem_buscas_retorna_1(self):
        db = self._make_db([])
        self.assertEqual(_get_next_busca_number(db, 1), 1)

    def test_apos_busca_1_retorna_2(self):
        db = self._make_db([(1,)])
        self.assertEqual(_get_next_busca_number(db, 1), 2)

    def test_apos_buscas_1_2_3_retorna_4(self):
        db = self._make_db([(1,), (2,), (3,)])
        self.assertEqual(_get_next_busca_number(db, 1), 4)

    def test_numeros_fora_de_ordem(self):
        db = self._make_db([(3,), (1,), (2,)])
        self.assertEqual(_get_next_busca_number(db, 1), 4)

    def test_ignora_none_na_lista(self):
        db = self._make_db([(1,), (None,), (3,)])
        self.assertEqual(_get_next_busca_number(db, 1), 4)


# ─── resolve_campanha_reference ───────────────────────────────────────────────

class TestResolveCampanhaReference(unittest.TestCase):
    """
    resolve_campanha_reference faz:
        query = db.query(Campanha).filter(Campanha.deleted_at.is_(None))
        campanha = query.filter(Campanha.codigo == ref).first()
        # se None e ref numérico:
        return query.filter(Campanha.id == id).first()

    Cadeia: db.query() → .filter() → .filter() → .first()
    Como todos os .filter() retornam o mesmo objeto (fluent_query),
    podemos usar side_effect no .first() para simular busca-por-código
    vs busca-por-id.
    """

    def test_ref_vazia_retorna_none(self):
        db = MagicMock()
        self.assertIsNone(resolve_campanha_reference("", db))
        self.assertIsNone(resolve_campanha_reference(None, db))
        db.query.assert_not_called()

    def test_busca_por_codigo_string(self):
        campanha = make_campanha(codigo="MASC-01")
        db = MagicMock()
        q = fluent_query(final_result=campanha)
        db.query.return_value = q

        result = resolve_campanha_reference("MASC-01", db)
        self.assertEqual(result, campanha)

    def test_busca_por_id_numerico_quando_codigo_nao_encontrado(self):
        campanha = make_campanha(id=5)
        db = MagicMock()
        q = fluent_query()
        # primeira chamada a .first() → None (não achou por código)
        # segunda chamada a .first() → campanha (achou por ID)
        q.first.side_effect = [None, campanha]
        db.query.return_value = q

        result = resolve_campanha_reference("5", db)
        self.assertEqual(result, campanha)

    def test_string_nao_numerica_sem_match_retorna_none(self):
        db = MagicMock()
        q = fluent_query(final_result=None)
        db.query.return_value = q

        result = resolve_campanha_reference("CODIGO-INEXISTENTE", db)
        self.assertIsNone(result)

    def test_id_numerico_inexistente_retorna_none(self):
        db = MagicMock()
        q = fluent_query()
        q.first.side_effect = [None, None]
        db.query.return_value = q

        result = resolve_campanha_reference("999", db)
        self.assertIsNone(result)


# ─── get_or_create_estacao ────────────────────────────────────────────────────

class TestGetOrCreateEstacao(unittest.TestCase):
    """
    get_or_create_estacao faz duas queries independentes:
      1. db.query(EspacoAmostral).filter(...).first()   → espaco
      2. db.query(EstacaoAmostral).filter(...).first()  → estacao

    Usamos db.query.side_effect para retornar um mock diferente
    dependendo do modelo passado.
    """

    def _setup_db(self, espaco=None, estacao=None) -> MagicMock:
        db = MagicMock()

        def query_side_effect(model):
            if model is EspacoAmostral:
                return fluent_query(final_result=espaco)
            if model is EstacaoAmostral:
                return fluent_query(final_result=estacao)
            return fluent_query()

        db.query.side_effect = query_side_effect
        return db

    def test_espaco_nao_encontrado_lanca_404(self):
        campanha = make_campanha()
        db = self._setup_db(espaco=None)
        with self.assertRaises(HTTPException) as ctx:
            get_or_create_estacao(campanha, 999, db)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_estacao_existente_e_retornada(self):
        campanha = make_campanha(id=1)
        espaco = make_espaco(id=10)
        estacao_existente = make_estacao(id=100)
        db = self._setup_db(espaco=espaco, estacao=estacao_existente)

        result = get_or_create_estacao(campanha, 10, db)

        self.assertEqual(result, estacao_existente)
        db.add.assert_not_called()
        db.flush.assert_not_called()

    def test_estacao_nova_e_criada_e_adicionada(self):
        campanha = make_campanha(id=1)
        espaco = make_espaco(id=10)
        db = self._setup_db(espaco=espaco, estacao=None)

        result = get_or_create_estacao(campanha, 10, db)

        db.add.assert_called_once()
        db.flush.assert_called_once()
        added = db.add.call_args[0][0]
        self.assertEqual(added.campanha_id, 1)
        self.assertEqual(added.espaco_amostral_id, 10)

    def test_segunda_chamada_reutiliza_estacao(self):
        campanha = make_campanha(id=1)
        espaco = make_espaco(id=10)
        estacao = make_estacao(id=100)

        # Primeira chamada: estação não existe → cria
        db1 = self._setup_db(espaco=espaco, estacao=None)
        get_or_create_estacao(campanha, 10, db1)
        self.assertEqual(db1.add.call_count, 1)

        # Segunda chamada: estação já existe → reutiliza, não duplica
        db2 = self._setup_db(espaco=espaco, estacao=estacao)
        result2 = get_or_create_estacao(campanha, 10, db2)
        db2.add.assert_not_called()
        self.assertEqual(result2, estacao)


# ─── resolve_estacao_for_campanha ─────────────────────────────────────────────

class TestResolveEstacaoForCampanha(unittest.TestCase):
    """
    resolve_estacao_for_campanha chama ensure_campanha_exists (que chama
    resolve_campanha_reference) e depois get_or_create_estacao ou consulta
    EstacaoAmostral diretamente.

    A cadeia de queries:
      Campanha:        db.query(Campanha).filter().filter().first()
      EspacoAmostral:  db.query(EspacoAmostral).filter().first()
      EstacaoAmostral: db.query(EstacaoAmostral).filter().first()
                    ou db.query(EstacaoAmostral).filter().order_by().all()

    Todos os .filter() são fluentes (retornam self), então um único
    fluent_query por modelo é suficiente.
    """

    def _setup_db(
        self,
        campanha=None,
        espaco=None,
        estacao=None,
        estacoes_list=None,
    ) -> MagicMock:
        db = MagicMock()

        def query_se(model):
            if model is Campanha:
                return fluent_query(final_result=campanha)
            if model is EspacoAmostral:
                return fluent_query(final_result=espaco)
            if model is EstacaoAmostral:
                q = fluent_query(
                    final_result=estacao,
                    all_result=estacoes_list if estacoes_list is not None else (
                        [estacao] if estacao else []
                    ),
                )
                return q
            return fluent_query()

        db.query.side_effect = query_se
        return db

    def test_novo_fluxo_com_espaco_amostral_id(self):
        campanha = make_campanha(id=1, codigo="MASC-01")
        espaco = make_espaco(id=10)
        estacao = make_estacao(id=100)
        db = self._setup_db(campanha=campanha, espaco=espaco, estacao=estacao)

        c, est = resolve_estacao_for_campanha("MASC-01", db, espaco_amostral_id=10)
        self.assertEqual(c, campanha)
        self.assertEqual(est, estacao)

    def test_novo_fluxo_cria_estacao_se_nao_existir(self):
        campanha = make_campanha(id=1, codigo="MASC-01")
        espaco = make_espaco(id=10)
        db = self._setup_db(campanha=campanha, espaco=espaco, estacao=None)

        c, est = resolve_estacao_for_campanha("MASC-01", db, espaco_amostral_id=10)
        self.assertEqual(c, campanha)
        db.add.assert_called_once()

    def test_novo_fluxo_espaco_invalido_lanca_404(self):
        campanha = make_campanha(id=1, codigo="MASC-01")
        db = self._setup_db(campanha=campanha, espaco=None, estacao=None)

        with self.assertRaises(HTTPException) as ctx:
            resolve_estacao_for_campanha("MASC-01", db, espaco_amostral_id=999)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_campanha_inexistente_lanca_404(self):
        db = self._setup_db(campanha=None)

        with self.assertRaises(HTTPException) as ctx:
            resolve_estacao_for_campanha("NAO-EXISTE", db, espaco_amostral_id=10)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_fluxo_legado_com_estacao_amostral_id(self):
        campanha = make_campanha(id=1, codigo="MASC-01")
        estacao = make_estacao(id=100, campanha_id=1)
        db = self._setup_db(campanha=campanha, estacao=estacao)

        c, est = resolve_estacao_for_campanha("MASC-01", db, estacao_amostral_id=100)
        self.assertEqual(c, campanha)
        self.assertEqual(est, estacao)
        db.add.assert_not_called()

    def test_fluxo_legado_sem_id_com_uma_estacao(self):
        """Sem nenhum ID, campanha com exatamente 1 estação → usa ela."""
        campanha = make_campanha(id=1, codigo="MASC-01")
        estacao = make_estacao(id=100, campanha_id=1)
        db = self._setup_db(campanha=campanha, estacao=estacao, estacoes_list=[estacao])

        c, est = resolve_estacao_for_campanha("MASC-01", db)
        self.assertEqual(est, estacao)

    def test_fluxo_legado_sem_id_com_multiplas_estacoes_lanca_400(self):
        campanha = make_campanha(id=1, codigo="MASC-01")
        estacoes = [make_estacao(id=i) for i in [100, 101]]
        db = self._setup_db(campanha=campanha, estacoes_list=estacoes)

        with self.assertRaises(HTTPException) as ctx:
            resolve_estacao_for_campanha("MASC-01", db)
        self.assertEqual(ctx.exception.status_code, 400)


# ─── runner sem pytest ────────────────────────────────────────────────────────

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for cls in [
        TestToFloat,
        TestNormalizeDatetime,
        TestNormalizeUrlList,
        TestGetNextBuscaNumber,
        TestResolveCampanhaReference,
        TestGetOrCreateEstacao,
        TestResolveEstacaoForCampanha,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
