"""Servicio que interpreta pedidos. La API solo depende del protocolo `Interpretador`, así que
las pruebas inyectan uno falso y no llaman al modelo.

Flujo (una sola llamada al modelo):
  mensajes → extraer (LLM) → resolver contra catálogo → consolidar (§2–§3)
           → calcular_pedido (§4–§8) → redactar confirmación (§9)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from pedidos.confirmacion import redactar
from pedidos.consolidacion import consolidar
from pedidos.datos import Datos
from pedidos.esquemas import RespuestaPedido, SolicitudPedido
from pedidos.extractor import Extraccion, ErrorExtraccion, extraer, resolver
from pedidos.reglas import PedidoCalculado, calcular_pedido

log = logging.getLogger("pedidos.servicio")


class ErrorModelo(RuntimeError):
    """El modelo no respondió a tiempo, respondió con error o con una salida inválida.
    La API responde 503: nunca se inventa un pedido."""


class Interpretador(Protocol):
    def interpretar(self, solicitud: SolicitudPedido) -> RespuestaPedido: ...


class InterpretadorPendiente:
    """Se usa cuando no se puede crear el modelo (p. ej. falta la clave)."""

    def __init__(self, motivo: str = "El interpretador de pedidos no está disponible."):
        self.motivo = motivo

    def interpretar(self, solicitud: SolicitudPedido) -> RespuestaPedido:
        raise ErrorModelo(self.motivo)


@dataclass
class Detalle:
    """Lo que pasó dentro de una solicitud (para trazas y evaluación)."""

    extraccion: Extraccion | None = None
    latencia_llm_s: float = 0.0
    uso: dict[str, Any] = field(default_factory=dict)
    pedido: PedidoCalculado | None = None


def armar_respuesta(cliente_id: str, pedido: PedidoCalculado, mensaje: str) -> RespuestaPedido:
    return RespuestaPedido(
        cliente_id=cliente_id, estado=pedido.estado, lineas=pedido.lineas,
        total=float(pedido.total), fecha_entrega=pedido.fecha_entrega,
        sustituciones=pedido.sustituciones, pendientes=pedido.pendientes,
        motivos_revision=pedido.motivos_revision, mensaje_cliente=mensaje,
    )


def interpretar_extraccion(
    solicitud: SolicitudPedido, extraccion: Extraccion, datos: Datos
) -> PedidoCalculado:
    """Todo lo que ocurre después del modelo: código puro y determinista."""
    es_pedido, menciones, pendientes = resolver(extraccion, datos, solicitud.mensajes)
    if not es_pedido:
        menciones, pendientes = [], []
    items, pend_consolidacion = consolidar(menciones, datos, solicitud.cliente_id)
    return calcular_pedido(solicitud.cliente_id, solicitud.recibido, items,
                           pendientes + pend_consolidacion, datos)


class InterpretadorLLM:
    def __init__(self, datos: Datos, llm_estructurado, cache: bool = True):
        self.datos = datos
        self.llm = llm_estructurado
        self.cache = cache

    def interpretar_con_detalle(self, solicitud: SolicitudPedido
                                ) -> tuple[RespuestaPedido, Detalle]:
        try:
            r = extraer(self.llm, self.datos, solicitud.mensajes, cache=self.cache)
        except ErrorExtraccion as e:
            raise ErrorModelo(str(e)) from e
        pedido = interpretar_extraccion(solicitud, r.extraccion, self.datos)
        mensaje = redactar(pedido, self.datos, solicitud.recibido)
        detalle = Detalle(extraccion=r.extraccion, latencia_llm_s=r.latencia_s, uso=r.uso,
                          pedido=pedido)
        return armar_respuesta(solicitud.cliente_id, pedido, mensaje), detalle

    def interpretar(self, solicitud: SolicitudPedido) -> RespuestaPedido:
        return self.interpretar_con_detalle(solicitud)[0]
