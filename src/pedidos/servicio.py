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
from pedidos.observabilidad import NULA, Observabilidad, costo_usd
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
    costo_usd: float | None = None
    trace_id: str | None = None


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


VERSION_PROMPT = "v3"


class InterpretadorLLM:
    def __init__(self, datos: Datos, llm_estructurado, cache: bool = True,
                 obs: Observabilidad = NULA, modelo: str = "", proveedor: str = "",
                 etiquetas: dict[str, str] | None = None):
        self.datos = datos
        self.llm = llm_estructurado
        self.cache = cache
        self.obs = obs
        self.modelo = modelo
        self.proveedor = proveedor
        self.etiquetas = etiquetas or {}

    def interpretar_con_detalle(self, solicitud: SolicitudPedido,
                                etiquetas: dict[str, str] | None = None
                                ) -> tuple[RespuestaPedido, Detalle]:
        obs = self.obs
        entradas = solicitud.model_dump()
        with obs.span("interpretar_pedido", "CHAIN", entradas, raiz=True) as raiz:
            obs.etiquetar({"cliente_id": solicitud.cliente_id, "modelo": self.modelo,
                           "proveedor": self.proveedor, "version_prompt": VERSION_PROMPT,
                           **self.etiquetas, **(etiquetas or {})})
            with obs.span("extraer", "CHAT_MODEL", {"mensajes": solicitud.mensajes}) as s:
                try:
                    r = extraer(self.llm, self.datos, solicitud.mensajes, cache=self.cache)
                except ErrorExtraccion as e:
                    s.set_attribute("error", str(e)[:300])
                    obs.etiquetar({"estado": "error_modelo"})
                    raise ErrorModelo(str(e)) from e
                costo = costo_usd(r.uso, self.modelo, obs.precios)
                s.set_outputs(r.extraccion.model_dump())
                s.set_attributes({"modelo": self.modelo, "proveedor": self.proveedor,
                                  "latencia_s": round(r.latencia_s, 3),
                                  "tokens": r.uso, "costo_usd": costo})
            with obs.span("reglas", "CHAIN") as s:
                pedido = interpretar_extraccion(solicitud, r.extraccion, self.datos)
                s.set_outputs({"estado": pedido.estado.value, "total": float(pedido.total),
                               "lineas": [l.model_dump() for l in pedido.lineas],
                               "pendientes": [p.model_dump(mode="json")
                                              for p in pedido.pendientes]})
            with obs.span("confirmacion", "CHAIN") as s:
                mensaje = redactar(pedido, self.datos, solicitud.recibido)
                s.set_outputs(mensaje)
            respuesta = armar_respuesta(solicitud.cliente_id, pedido, mensaje)
            raiz.set_outputs(respuesta.model_dump(mode="json"))
            raiz.set_attributes({"total": float(pedido.total), "costo_usd": costo,
                                 "latencia_llm_s": round(r.latencia_s, 3),
                                 "motivos": [m.value for m in pedido.motivos_revision]})
            obs.etiquetar({"estado": pedido.estado.value})
        detalle = Detalle(extraccion=r.extraccion, latencia_llm_s=r.latencia_s, uso=r.uso,
                          pedido=pedido, costo_usd=costo, trace_id=obs.ultimo_trace_id)
        return respuesta, detalle

    def interpretar(self, solicitud: SolicitudPedido) -> RespuestaPedido:
        return self.interpretar_con_detalle(solicitud)[0]
