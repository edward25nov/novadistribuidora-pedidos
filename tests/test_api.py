"""Contrato de la API con un interpretador falso: no se llama al modelo."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pedidos.api import crear_app
from pedidos.esquemas import RespuestaPedido, SolicitudPedido
from pedidos.servicio import ErrorModelo

VALIDA = {
    "cliente_id": "C001",
    "fecha_hora": "2026-11-23T15:20",
    "mensajes": ["Buenas, mándeme 2 fardos de kola 600"],
}


class InterpretadorFijo:
    def __init__(self):
        self.llamadas = 0

    def interpretar(self, s: SolicitudPedido) -> RespuestaPedido:
        self.llamadas += 1
        return RespuestaPedido(
            cliente_id=s.cliente_id, estado="confirmado",
            lineas=[{"sku": "B01", "cantidad": 2, "precio_unitario": 120.0,
                     "descuento_pct": 0, "subtotal": 240.0}],
            total=240.0, fecha_entrega="2026-11-26", sustituciones=[], pendientes=[],
            motivos_revision=[], mensaje_cliente="¡Gracias! Recibimos su pedido.",
        )


class InterpretadorQueFalla:
    def interpretar(self, s):
        raise ErrorModelo("timeout")


class MlflowFalso:
    def __init__(self, estado="ok"):
        self._estado = estado

    def estado(self):
        return self._estado


@pytest.fixture
def interpretador():
    return InterpretadorFijo()


@pytest.fixture
def cliente(datos_mini, interpretador):
    app = crear_app(datos=datos_mini, interpretador=interpretador, verificador_mlflow=MlflowFalso())
    return TestClient(app, raise_server_exceptions=False)


def test_interpretar_ok(cliente):
    r = cliente.post("/v1/pedidos/interpretar", json=VALIDA)
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo) == {
        "cliente_id", "estado", "lineas", "total", "fecha_entrega", "sustituciones",
        "pendientes", "motivos_revision", "mensaje_cliente",
    }
    assert cuerpo["fecha_entrega"] == "2026-11-26"
    assert cuerpo["lineas"][0]["subtotal"] == 240.0


def test_cliente_inexistente_404(cliente, interpretador):
    r = cliente.post("/v1/pedidos/interpretar", json={**VALIDA, "cliente_id": "C999"})
    assert r.status_code == 404
    assert "C999" in r.json()["detail"]
    assert interpretador.llamadas == 0


@pytest.mark.parametrize(
    "cambio, fragmento",
    [
        ({"mensajes": []}, "mensajes no puede estar vacío"),
        ({"mensajes": ["   "]}, "el mensaje 0 está vacío"),
        ({"mensajes": ["x" * 2001]}, "supera 2000 caracteres"),
        ({"mensajes": ["a"] * 21}, "como máximo 20 mensajes"),
        ({"mensajes": "hola"}, "mensajes debe ser una lista"),
        ({"fecha_hora": "2026-11-23 15:20"}, "formato AAAA-MM-DDTHH:MM"),
        ({"fecha_hora": "23/11/2026T15:20"}, "formato AAAA-MM-DDTHH:MM"),
        ({"fecha_hora": "2026-13-23T15:20"}, "no es una fecha y hora válida"),
        ({"fecha_hora": "2026-11-23T15:20:00"}, "formato AAAA-MM-DDTHH:MM"),
        ({"cliente_id": "  "}, "cliente_id no puede estar vacío"),
        ({"cliente_id": 123}, "cliente_id debe ser texto"),
    ],
)
def test_solicitud_invalida_422(cliente, cambio, fragmento):
    r = cliente.post("/v1/pedidos/interpretar", json={**VALIDA, **cambio})
    assert r.status_code == 422
    assert fragmento in r.json()["detail"]


@pytest.mark.parametrize("campo", ["cliente_id", "fecha_hora", "mensajes"])
def test_campo_faltante_422(cliente, campo):
    cuerpo = {k: v for k, v in VALIDA.items() if k != campo}
    r = cliente.post("/v1/pedidos/interpretar", json=cuerpo)
    assert r.status_code == 422
    assert f"falta el campo obligatorio {campo}" in r.json()["detail"]


def test_cuerpo_no_json_422(cliente):
    r = cliente.post(
        "/v1/pedidos/interpretar", content="no es json",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422
    assert "JSON" in r.json()["detail"]


def test_inexistente_e_invalido_da_422_no_404(cliente):
    r = cliente.post("/v1/pedidos/interpretar", json={"cliente_id": "C999", "mensajes": []})
    assert r.status_code == 422


def test_falla_del_modelo_503(datos_mini):
    app = crear_app(datos=datos_mini, interpretador=InterpretadorQueFalla(),
                    verificador_mlflow=MlflowFalso())
    r = TestClient(app, raise_server_exceptions=False).post("/v1/pedidos/interpretar", json=VALIDA)
    assert r.status_code == 503
    assert "modelo" in r.json()["detail"]


def test_error_inesperado_500_controlado(datos_mini):
    class Roto:
        def interpretar(self, s):
            raise KeyError("bug")

    app = crear_app(datos=datos_mini, interpretador=Roto(), verificador_mlflow=MlflowFalso())
    r = TestClient(app, raise_server_exceptions=False).post("/v1/pedidos/interpretar", json=VALIDA)
    assert r.status_code == 500
    assert r.json() == {"detail": "Error interno del servicio."}


def test_health_ok(cliente):
    r = cliente.get("/health")
    assert r.status_code == 200
    assert r.json()["estado"] == "ok"
    assert r.json()["motivo"] is None


def test_health_degradado_sin_mlflow(datos_mini, interpretador):
    app = crear_app(datos=datos_mini, interpretador=interpretador,
                    verificador_mlflow=MlflowFalso("no disponible (ConnectError)"))
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["estado"] == "degradado"
    assert "mlflow" in r.json()["motivo"]
    # la API sigue respondiendo pedidos con MLflow caído
    assert c.post("/v1/pedidos/interpretar", json=VALIDA).status_code == 200


def test_health_degradado_sin_api_key(datos_mini, interpretador):
    app = crear_app(datos=datos_mini, interpretador=interpretador,
                    verificador_mlflow=MlflowFalso(), falta_api_key="falta ANTHROPIC_API_KEY")
    r = TestClient(app).get("/health")
    assert r.json()["estado"] == "degradado"
    assert "ANTHROPIC_API_KEY" in r.json()["motivo"]


def test_sin_datos_arranca_degradado_y_503(tmp_path, monkeypatch):
    monkeypatch.setenv("RUTA_DATOS", str(tmp_path / "no-existe"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-prueba")
    c = TestClient(crear_app())
    salud = c.get("/health").json()
    assert salud["estado"] == "degradado"
    assert "datos" in salud["motivo"]
    r = c.post("/v1/pedidos/interpretar", json=VALIDA)
    assert r.status_code == 503
    assert "no-existe" in r.json()["detail"] and "README" in r.json()["detail"]


@pytest.mark.parametrize(
    "variable, valor",
    [("PROVEEDOR_LLM", "openai"), ("LLM_TIMEOUT_S", "abc"), ("LLM_ESFUERZO", "x")],
)
def test_config_invalida_arranca_degradado_y_503(monkeypatch, variable, valor):
    monkeypatch.setenv(variable, valor)
    c = TestClient(crear_app())
    salud = c.get("/health").json()
    assert salud["estado"] == "degradado"
    assert salud["motivo"].startswith("config: ") and variable in salud["motivo"]
    r = c.post("/v1/pedidos/interpretar", json=VALIDA)
    assert r.status_code == 503
    assert variable in r.json()["detail"]


def test_503_no_filtra_detalle_del_proveedor(datos_mini):
    class FallaConDetalle:
        def interpretar(self, s):
            raise ErrorModelo("Error code: 529 - {'type': 'overloaded_error', 'request_id': 'req_x'}")

    app = crear_app(datos=datos_mini, interpretador=FallaConDetalle(),
                    verificador_mlflow=MlflowFalso())
    r = TestClient(app).post("/v1/pedidos/interpretar", json=VALIDA)
    assert r.status_code == 503
    assert "req_x" not in r.text and "529" not in r.text
