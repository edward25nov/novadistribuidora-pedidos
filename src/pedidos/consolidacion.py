"""De menciones ya resueltas a SKU → ítems del pedido en unidades de venta.

Aplica, en código y sin modelo, las secciones 2 y 3 de politicas.md:
- §2 sin unidad = unidad de venta; sin cantidad = 1; unidades sueltas o docenas solo si la
  conversión es exacta (si no, pendiente `cantidad_no_convertible`, nunca se redondea);
  menciones repetidas se suman; una corrección explícita reemplaza; "quitar" elimina.
- §3 "lo de siempre" = líneas del último pedido `entregado`, con las mismas cantidades.

La suma se hace ANTES de convertir: se acumulan unidades sueltas por SKU y se convierte al final
(12 latas + 12 latas de un fardo de 24 = 1 fardo).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from pedidos.datos import Datos
from pedidos.esquemas import Motivo, Pendiente


class TipoUnidad(str, Enum):
    empaque = "empaque"     # fardo, caja, display, quintal… (la unidad de venta)
    suelta = "suelta"       # botellas, latas, bolsas, sobres, unidades…
    docena = "docena"
    ninguna = "ninguna"     # "3 de kola 600": se entiende la unidad de venta


class Accion(str, Enum):
    agregar = "agregar"
    corregir = "corregir"   # "no, mejor que sean 5": reemplaza la cantidad anterior
    quitar = "quitar"       # "pero sin las papalinas"


@dataclass(frozen=True)
class MencionResuelta:
    """Una mención cuyo producto ya se resolvió a un SKU del catálogo."""

    texto: str
    sku: str
    cantidad: Decimal | None = None
    unidad: TipoUnidad = TipoUnidad.ninguna
    accion: Accion = Accion.agregar


@dataclass(frozen=True)
class MencionHabitual:
    """'Lo de siempre', 'lo mismo de la otra vez'…"""

    texto: str


@dataclass(frozen=True)
class MencionQuitarAmbigua:
    """'Quíteme la kola' cuando el texto puede ser varios SKU. Se resuelve contra lo que ya está
    en el pedido: si está uno solo, se quita ese; si están 2 o más, no se adivina (pendiente
    producto_ambiguo con los presentes); si no está ninguno, no cambia nada."""

    texto: str
    candidatos: tuple[str, ...]


@dataclass(frozen=True)
class ItemPedido:
    sku: str          # SKU solicitado (antes de sustituir agotados)
    cantidad: int     # en unidades de venta, > 0
    texto: str


@dataclass
class _Acumulado:
    texto: str
    sueltas: Decimal = Decimal(0)   # todo se lleva a unidades sueltas
    invalida: bool = False          # alguna mención con cantidad <= 0 ("menos 3 fardos")


def unidades_sueltas(cantidad: Decimal | None, unidad: TipoUnidad, upe: int) -> Decimal:
    """Convierte una cantidad mencionada a unidades sueltas."""
    n = Decimal(1) if cantidad is None else Decimal(cantidad)
    if unidad is TipoUnidad.suelta:
        return n
    if unidad is TipoUnidad.docena:
        return n * 12
    return n * upe        # empaque o sin unidad: unidad de venta


def a_unidades_de_venta(sueltas: Decimal, upe: int) -> int | None:
    """Unidades de venta si la conversión es exacta y positiva; si no, None."""
    if sueltas <= 0:
        return None
    cociente = sueltas / upe
    if cociente != cociente.to_integral_value():
        return None
    return int(cociente)


def consolidar(
    menciones: list[MencionResuelta | MencionHabitual | MencionQuitarAmbigua],
    datos: Datos,
    cliente_id: str,
) -> tuple[list[ItemPedido], list[Pendiente]]:
    acumulado: dict[str, _Acumulado] = {}
    pendientes: list[Pendiente] = []

    def sumar(sku: str, texto: str, sueltas: Decimal, reemplazar: bool) -> None:
        if sku not in acumulado:
            acumulado[sku] = _Acumulado(texto=texto)
        a = acumulado[sku]
        if reemplazar:
            a.sueltas, a.texto, a.invalida = sueltas, texto, False
        else:
            a.sueltas += sueltas
        if sueltas <= 0:
            # Una cantidad cero o negativa no se resta ni se ignora: va a revisión.
            a.invalida, a.texto = True, texto

    for m in menciones:
        if isinstance(m, MencionQuitarAmbigua):
            presentes = [s for s in m.candidatos if s in acumulado]
            if len(presentes) == 1:
                acumulado.pop(presentes[0])
            elif len(presentes) > 1:
                pendientes.append(Pendiente(motivo=Motivo.producto_ambiguo, texto=m.texto,
                                            opciones=sorted(presentes)))
            continue

        if isinstance(m, MencionHabitual):
            lineas = datos.ultimo_pedido_entregado(cliente_id)
            if not lineas:
                # Sin pedido entregado no hay "lo de siempre" que copiar: no se adivina.
                pendientes.append(
                    Pendiente(motivo=Motivo.producto_ambiguo, texto=m.texto, opciones=[])
                )
                continue
            for sku, cantidad in lineas:
                if sku not in datos.catalogo:
                    # Un SKU histórico que ya no se vende: no se inventa ni se descarta en silencio.
                    pendientes.append(Pendiente(motivo=Motivo.producto_no_existe,
                                                texto=f"{sku} (de {m.texto})", opciones=[]))
                    continue
                upe = datos.catalogo[sku].unidades_por_empaque
                sumar(sku, datos.catalogo[sku].nombre, Decimal(cantidad) * upe, False)
            continue

        if m.sku not in datos.catalogo:
            # Defensa en profundidad: la resolución ya valida contra el catálogo.
            pendientes.append(Pendiente(motivo=Motivo.producto_no_existe, texto=m.texto, opciones=[]))
            continue
        producto = datos.catalogo[m.sku]
        if m.accion is Accion.quitar:
            acumulado.pop(m.sku, None)
            continue
        sueltas = unidades_sueltas(m.cantidad, m.unidad, producto.unidades_por_empaque)
        sumar(m.sku, m.texto, sueltas, reemplazar=m.accion is Accion.corregir)

    items: list[ItemPedido] = []
    for sku, a in acumulado.items():
        cantidad = a_unidades_de_venta(a.sueltas, datos.catalogo[sku].unidades_por_empaque)
        if cantidad is None or a.invalida:
            pendientes.append(
                Pendiente(motivo=Motivo.cantidad_no_convertible, texto=a.texto, opciones=[sku])
            )
        else:
            items.append(ItemPedido(sku=sku, cantidad=cantidad, texto=a.texto))
    return items, pendientes
