import httpx

from pedidos import salud
from pedidos.salud import VerificadorMlflow


def test_no_configurado():
    assert VerificadorMlflow("").estado() == "no_configurado"


def test_caido_y_cache(monkeypatch):
    llamadas = []

    def get_falso(url, timeout):
        llamadas.append((url, timeout))
        raise httpx.ConnectError("conexión rechazada")

    t = [100.0]
    monkeypatch.setattr(salud.httpx, "get", get_falso)
    v = VerificadorMlflow("http://mlflow:5000/", reloj=lambda: t[0])
    assert v.estado() == "no disponible (ConnectError)"
    assert llamadas == [("http://mlflow:5000/health", salud.TIMEOUT_PING_S)]
    t[0] += 1
    v.estado()
    assert len(llamadas) == 1          # dentro de la ventana de cache no vuelve a llamar
    t[0] += salud.CACHE_S
    v.estado()
    assert len(llamadas) == 2


def test_ok(monkeypatch):
    monkeypatch.setattr(salud.httpx, "get", lambda url, timeout: httpx.Response(200))
    assert VerificadorMlflow("http://x").estado() == "ok"
