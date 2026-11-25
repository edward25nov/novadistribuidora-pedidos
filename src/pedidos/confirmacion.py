"""Mensaje de confirmación al cliente, armado con plantilla desde el pedido YA calculado (§9).

Determinista: no puede prometer productos agotados o pendientes ni mencionar precios distintos a
los calculados, porque solo usa los datos del pedido.
"""

from __future__ import annotations

from datetime import date, datetime

from pedidos.datos import Datos
from pedidos.esquemas import Estado, Motivo
from pedidos.reglas import PedidoCalculado

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]
_PLURAL = {"fardo": "fardos", "caja": "cajas", "display": "displays", "quintal": "quintales"}


def saludo(recibido: datetime) -> str:
    if recibido.hour < 12:
        return "¡Buenos días!"
    if recibido.hour < 19:
        return "¡Buenas tardes!"
    return "¡Buenas noches!"


def fecha_larga(d: date) -> str:
    return f"el {_DIAS[d.weekday()]} {d.day} de {_MESES[d.month - 1]}"


def cantidad_con_unidad(cantidad: int, unidad: str) -> str:
    u = unidad if cantidad == 1 else _PLURAL.get(unidad, unidad + "s")
    return f"{cantidad} {u}"


def _enumerar(partes: list[str]) -> str:
    if len(partes) <= 1:
        return "".join(partes)
    return ", ".join(partes[:-1]) + " y " + partes[-1]


def _quetzales(monto) -> str:
    return f"Q{monto:,.2f}"


def redactar(pedido: PedidoCalculado, datos: Datos, recibido: datetime) -> str:
    if pedido.estado is Estado.fuera_de_alcance:
        return (f"{saludo(recibido)} Gracias por escribirnos. Este número recibe pedidos; "
                "un asesor atenderá su consulta en breve.")

    partes = [saludo(recibido)]
    cat = datos.catalogo
    if pedido.lineas:
        items = [f"{cantidad_con_unidad(l.cantidad, cat[l.sku].unidad_venta)} de "
                 f"{cat[l.sku].nombre}" for l in pedido.lineas]
        partes.append(f"Recibimos su pedido: {_enumerar(items)}.")
    else:
        partes.append("Recibimos su mensaje.")
    for s in pedido.sustituciones:
        partes.append(f"{cat[s.sku_solicitado].nombre} está agotado; en su lugar le enviamos "
                      f"{cat[s.sku_entregado].nombre}.")
    if pedido.pendientes:
        textos = [f"«{p.texto}»" for p in pedido.pendientes]
        partes.append(f"Sobre {_enumerar(textos)}, un asesor le confirmará.")
    if Motivo.credito_excedido in pedido.motivos_revision:
        partes.append("Su pedido queda en revisión por el límite de crédito; un asesor lo "
                      "confirmará.")
    if pedido.lineas:
        partes.append(f"Total: {_quetzales(pedido.total)}.")
    if pedido.fecha_entrega:
        verbo = "Entrega" if pedido.estado is Estado.confirmado else "Entrega prevista"
        partes.append(f"{verbo} {fecha_larga(pedido.fecha_entrega)}.")
    partes.append("¡Gracias!")
    return " ".join(partes)
