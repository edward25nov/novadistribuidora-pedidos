"""Observabilidad: costo, no-op, MLflow caído y una traza real contra un MLflow local (SQLite)."""

from __future__ import annotations

import time

import pytest

from pedidos import observabilidad as obs_mod
from pedidos.esquemas import SolicitudPedido
from pedidos.extractor import Extraccion, MencionLLM
from pedidos.observabilidad import Observabilidad, cargar_precios, costo_usd
from pedidos.servicio import ErrorModelo, InterpretadorLLM
from test_extractor import LLMFalso

PRECIOS = cargar_precios()


def _solicitud():
    return SolicitudPedido(cliente_id="C001", fecha_hora="2026-11-23T10:00",
                           mensajes=["2 fardos de kola 600"])


def _ex():
    return Extraccion(es_pedido=True, menciones=[MencionLLM(
        texto="kola 600", tipo="producto", sku_candidatos=["B01"], cantidad=2,
        unidad="empaque", accion="agregar")])


# ---------- Costo ----------

def test_precios_cargados_con_los_tres_modelos():
    assert {"claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"} <= set(PRECIOS)


def test_costo_separa_cache_de_entrada():
    uso = {"input_tokens": 5000, "output_tokens": 200,
           "input_token_details": {"cache_read": 4900, "cache_creation": 0}}
    # 100 × 0.10 + 4900 × 0.01 + 200 × 0.50 = 10 + 49 + 100 = 159 por millón
    assert costo_usd(uso, "claude-haiku-5-5", PRECIOS) == pytest.approx(159e-6)


def test_costo_escritura_de_cache_y_id_de_openrouter():
    uso = {"input_tokens": 5000, "output_tokens": 0,
           "input_token_details": {"cache_read": 0, "cache_creation": 4914}}
    esperado = (86 * 0.10 + 4914 * 0.125) / 1e6
    assert costo_usd(uso, "anthropic/claude-haiku-5.5", PRECIOS) == pytest.approx(esperado)


def test_costo_modelo_desconocido_es_none():
    assert costo_usd({"input_tokens": 1}, "otro-modelo", PRECIOS) is None


# ---------- Sin MLflow ----------

def test_sin_uri_es_no_op(datos_mini):
    obs = Observabilidad("")
    assert not obs.activa
    resp, det = InterpretadorLLM(datos_mini, LLMFalso(_ex()), obs=obs,
                                 modelo="claude-haiku-5-5").interpretar_con_detalle(_solicitud())
    assert resp.total == 240.0 and det.trace_id is None


def test_mlflow_caido_no_frena_ni_rompe(datos_mini):
    obs = Observabilidad("http://127.0.0.1:5999", conectar_en_segundo_plano=False)
    assert not obs.activa
    interp = InterpretadorLLM(datos_mini, LLMFalso(_ex()), obs=obs, modelo="claude-haiku-5-5")
    inicio = time.perf_counter()
    for _ in range(5):
        assert interp.interpretar(_solicitud()).total == 240.0
    assert time.perf_counter() - inicio < 1.0


def test_span_propaga_errores_de_negocio(datos_mini):
    with pytest.raises(ErrorModelo):
        InterpretadorLLM(datos_mini, LLMFalso(error=TimeoutError("x")), obs=Observabilidad("")
                         ).interpretar(_solicitud())


# ---------- Con MLflow local ----------

@pytest.fixture
def mlflow_local(tmp_path, monkeypatch):
    mlflow = pytest.importorskip("mlflow")
    pytest.importorskip("mlflow.server")                 # requiere mlflow completo (dev)
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    obs = Observabilidad(uri, experimento="pruebas", conectar_en_segundo_plano=False)
    assert obs.activa
    yield mlflow, obs
    mlflow.set_tracking_uri("")


def test_traza_completa_con_spans_etiquetas_y_costo(datos_mini, mlflow_local):
    mlflow, obs = mlflow_local
    interp = InterpretadorLLM(datos_mini, LLMFalso(_ex()), obs=obs, modelo="claude-haiku-5-5",
                              proveedor="anthropic", etiquetas={"origen": "test"})
    resp, det = interp.interpretar_con_detalle(_solicitud(), etiquetas={"caso": "T1"})
    mlflow.flush_trace_async_logging()
    traza = mlflow.get_trace(det.trace_id)
    nombres = [s.name for s in traza.data.spans]
    assert nombres[0] == "interpretar_pedido"
    assert set(nombres) == {"interpretar_pedido", "extraer", "reglas", "confirmacion"}
    tags = traza.info.tags
    assert (tags["cliente_id"], tags["estado"], tags["modelo"], tags["caso"], tags["origen"]) == (
        "C001", "confirmado", "claude-haiku-5-5", "T1", "test")
    raiz = traza.data.spans[0]
    assert raiz.outputs["total"] == 240.0
    assert raiz.attributes["costo_usd"] == pytest.approx(det.costo_usd)
    assert det.costo_usd > 0


def test_error_del_modelo_queda_en_la_traza(datos_mini, mlflow_local):
    mlflow, obs = mlflow_local
    interp = InterpretadorLLM(datos_mini, LLMFalso(error=TimeoutError("lento")), obs=obs)
    with pytest.raises(ErrorModelo):
        interp.interpretar(_solicitud())
    mlflow.flush_trace_async_logging()
    trazas = mlflow.search_traces(return_type="list", max_results=1)
    assert trazas[0].info.tags["estado"] == "error_modelo"
    assert trazas[0].info.state.value == "ERROR"


# ---------- Conexión con espera creciente ----------

def test_bucle_de_conexion_con_espera_creciente(monkeypatch):
    obs = Observabilidad("http://127.0.0.1:5999", conectar_en_segundo_plano=False)
    intentos, esperas = [], []
    monkeypatch.setattr(obs, "_intentar_conectar",
                        lambda: intentos.append(1) or len(intentos) >= 7)
    monkeypatch.setattr(obs._despertar, "wait", lambda timeout: esperas.append(timeout))
    obs._bucle_conexion()
    assert esperas == [1, 2, 4, 8, 16, 30]          # tope en REINTENTO_S


def test_health_dice_conectando_y_despierta(datos_mini):
    from fastapi.testclient import TestClient

    from pedidos.api import crear_app

    class MlflowArriba:
        def estado(self):
            return "ok"

    obs = Observabilidad("http://127.0.0.1:5999", conectar_en_segundo_plano=False)
    interp = InterpretadorLLM(datos_mini, LLMFalso(_ex()), obs=obs)
    salud = TestClient(crear_app(datos=datos_mini, interpretador=interp,
                                 verificador_mlflow=MlflowArriba())).get("/health").json()
    assert salud["estado"] == "degradado" and salud["dependencias"]["mlflow"] == "conectando"
    assert obs._despertar.is_set()


# ---------- Una decisión por solicitud: sin trazas partidas ----------

class LLMQueConecta(LLMFalso):
    """Cambia el estado de la observabilidad a mitad de la solicitud."""

    def __init__(self, obs, listo):
        super().__init__(_ex())
        self.obs, self.listo = obs, listo

    def invoke(self, mensajes):
        self.obs._listo = self.listo
        return super().invoke(mensajes)


def test_reconexion_a_mitad_no_crea_trazas_huerfanas(datos_mini, mlflow_local):
    mlflow, obs = mlflow_local
    obs._listo = False                                   # al empezar la solicitud no traza
    interp = InterpretadorLLM(datos_mini, LLMQueConecta(obs, listo=True), obs=obs)
    assert interp.interpretar(_solicitud()).total == 240.0
    mlflow.flush_trace_async_logging()
    assert mlflow.search_traces(return_type="list", max_results=10) == []


def test_desconexion_a_mitad_mantiene_la_traza_completa(datos_mini, mlflow_local):
    mlflow, obs = mlflow_local
    interp = InterpretadorLLM(datos_mini, LLMQueConecta(obs, listo=False), obs=obs)
    interp.interpretar(_solicitud())
    mlflow.flush_trace_async_logging()
    trazas = mlflow.search_traces(return_type="list", max_results=10)
    assert len(trazas) == 1
    assert {s.name for s in trazas[0].data.spans} == {
        "interpretar_pedido", "extraer", "reglas", "confirmacion"}
