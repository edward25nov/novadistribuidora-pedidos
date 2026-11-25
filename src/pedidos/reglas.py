"""Motor de reglas: de ítems en unidades de venta al pedido calculado (politicas.md §4–§8).

Todo con Decimal. El modelo de lenguaje nunca produce ninguno de estos números.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from pedidos.consolidacion import ItemPedido
from pedidos.datos import Cliente, Datos, Producto
from pedidos.esquemas import Estado, Linea, Motivo, Pendiente, Sustitucion

CENTAVO = Decimal("0.01")
HORA_CORTE = time(14, 0)     # §7: a las 14:00 o después cuenta como recibido al día siguiente


# ---------- §5 precios y descuentos ----------

def descuento_pct(categoria: str, cantidad: int, escala) -> int:
    """Mayor porcentaje de la categoría cuyo mínimo se alcanza (cantidad >= mínimo), por línea."""
    filas = escala[(escala["categoria"] == categoria) & (escala["cantidad_minima"] <= cantidad)]
    return int(filas["descuento_pct"].max()) if not filas.empty else 0


def subtotal(cantidad: int, precio: Decimal, pct: int) -> Decimal:
    """cantidad × precio × (1 − pct/100), redondeado a 2 decimales mitad hacia arriba."""
    bruto = Decimal(cantidad) * precio * (Decimal(100) - Decimal(pct)) / Decimal(100)
    return bruto.quantize(CENTAVO, rounding=ROUND_HALF_UP)


# ---------- §7 fecha de entrega ----------

def fecha_efectiva(recibido: datetime) -> date:
    return recibido.date() + timedelta(days=1) if recibido.time() >= HORA_CORTE else recibido.date()


def fecha_entrega(recibido: datetime, dias_visita: tuple[int, ...]) -> date:
    """Primera visita de la ruta POSTERIOR a la fecha de recepción (efectiva). Sin feriados."""
    base = fecha_efectiva(recibido)
    for delta in range(1, 8):
        d = base + timedelta(days=delta)
        if d.weekday() in dias_visita:
            return d
    raise ValueError("el cliente no tiene días de visita")


# ---------- §6 crédito ----------

def credito_excedido(cliente: Cliente, total: Decimal) -> bool:
    """Requiere revisión si saldo_pendiente + total SUPERA el límite (igual no excede)."""
    return cliente.saldo_pendiente + total > cliente.limite_credito


# ---------- §4 agotados y sustitutos ----------

def producto_a_entregar(sku: str, catalogo: dict[str, Producto]) -> Producto | None:
    """El producto si está disponible; si no, su sustituto si existe y está disponible.
    Nunca encadena sustituciones: un sustituto agotado o inexistente → None."""
    p = catalogo[sku]
    if p.disponible:
        return p
    if p.sustituto_sku and p.sustituto_sku in catalogo and catalogo[p.sustituto_sku].disponible:
        return catalogo[p.sustituto_sku]
    return None


@dataclass
class PedidoCalculado:
    estado: Estado
    lineas: list[Linea]
    total: Decimal
    fecha_entrega: date | None
    sustituciones: list[Sustitucion]
    pendientes: list[Pendiente]
    motivos_revision: list[Motivo]


def calcular_pedido(
    cliente_id: str,
    recibido: datetime,
    items: list[ItemPedido],
    pendientes: list[Pendiente],
    datos: Datos,
) -> PedidoCalculado:
    """§4–§8. `pendientes` trae los de la interpretación (ambiguos, no existe, no convertible)."""
    cliente = datos.cliente(cliente_id)
    pendientes = list(pendientes)
    cantidades: dict[str, int] = {}           # sku entregado → cantidad (orden de aparición)
    sustituciones: list[Sustitucion] = []

    for item in items:
        entregado = producto_a_entregar(item.sku, datos.catalogo)
        if entregado is None:
            pendientes.append(
                Pendiente(motivo=Motivo.agotado_sin_sustituto,
                          texto=datos.catalogo[item.sku].nombre, opciones=[item.sku])
            )
            continue
        if entregado.sku != item.sku:
            sustituciones.append(Sustitucion(sku_solicitado=item.sku,
                                             sku_entregado=entregado.sku,
                                             cantidad=item.cantidad))
        # Si el sustituto también se pidió directamente, es una sola línea (§2: se suman).
        cantidades[entregado.sku] = cantidades.get(entregado.sku, 0) + item.cantidad

    lineas: list[Linea] = []
    total = Decimal(0)
    for sku, cantidad in cantidades.items():
        p = datos.catalogo[sku]
        pct = descuento_pct(p.categoria, cantidad, datos.escala)
        st = subtotal(cantidad, p.precio, pct)
        total += st
        lineas.append(Linea(sku=sku, cantidad=cantidad, precio_unitario=float(p.precio),
                            descuento_pct=pct, subtotal=float(st)))

    if not lineas and not pendientes:
        # §8: sin pedido → fuera de alcance, sin líneas, total 0 y sin fecha.
        return PedidoCalculado(Estado.fuera_de_alcance, [], Decimal(0), None, [], [], [])

    motivos: list[Motivo] = []
    for p in pendientes:
        if p.motivo not in motivos:
            motivos.append(p.motivo)
    if credito_excedido(cliente, total):
        motivos.append(Motivo.credito_excedido)

    estado = Estado.requiere_revision if motivos else Estado.confirmado
    return PedidoCalculado(
        estado=estado, lineas=lineas, total=total.quantize(CENTAVO),
        fecha_entrega=fecha_entrega(recibido, cliente.dias_visita),
        sustituciones=sustituciones, pendientes=pendientes, motivos_revision=motivos,
    )
