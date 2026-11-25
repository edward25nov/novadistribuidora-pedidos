"""Interfaz del servicio que interpreta pedidos. La API solo depende de este protocolo, así que
las pruebas inyectan uno falso y no llaman al modelo."""

from __future__ import annotations

from typing import Protocol

from pedidos.esquemas import RespuestaPedido, SolicitudPedido


class ErrorModelo(RuntimeError):
    """El modelo no respondió a tiempo, respondió con error o con una salida inválida.
    La API responde 503: nunca se inventa un pedido."""


class Interpretador(Protocol):
    def interpretar(self, solicitud: SolicitudPedido) -> RespuestaPedido: ...


class InterpretadorPendiente:
    """Marcador hasta que existan el motor de reglas (fase 2) y el extractor (fase 3)."""

    def interpretar(self, solicitud: SolicitudPedido) -> RespuestaPedido:
        raise ErrorModelo("El interpretador de pedidos aún no está implementado.")
