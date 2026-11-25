"""Motor de reglas. Cada prueba cita la sección de politicas.md que verifica."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from pedidos.consolidacion import ItemPedido
from pedidos.esquemas import Estado, Motivo, Pendiente
from pedidos.reglas import (
    calcular_pedido, credito_excedido, descuento_pct, fecha_efectiva, fecha_entrega,
    producto_a_entregar, subtotal,
)

LUN_JUE = (0, 3)
SAB = (5,)


def _calc(datos, items, pendientes=(), cliente="C001", recibido="2026-11-23T10:00"):
    return calcular_pedido(cliente, datetime.fromisoformat(recibido),
                           [ItemPedido(s, c, s) for s, c in items], list(pendientes), datos)


# ---------- §5 Precios y descuentos ----------

@pytest.mark.parametrize(
    "cantidad, esperado",
    [(1, 0), (9, 0), (10, 3), (19, 3), (20, 5), (100, 5)],   # el mínimo se alcanza con >=
)
def test_s5_descuento_mayor_porcentaje_alcanzado(datos_mini, cantidad, esperado):
    assert descuento_pct("bebidas", cantidad, datos_mini.escala) == esperado


def test_s5_categoria_sin_escala_no_tiene_descuento(datos_mini):
    assert descuento_pct("limpieza", 50, datos_mini.escala) == 0


def test_s5_descuento_es_por_linea_no_por_categoria_acumulada(datos_mini):
    # 6 + 6 fardos de bebidas distintas: ninguna línea llega a 10 → sin descuento
    r = _calc(datos_mini, [("B01", 6), ("B02", 6)])
    assert [l.descuento_pct for l in r.lineas] == [0, 0]


@pytest.mark.parametrize(
    "cantidad, precio, pct, esperado",
    [
        (10, "156", 4, "1497.60"),       # D005
        (6, "216", 3, "1257.12"),        # D032
        (1, "0.125", 0, "0.13"),         # mitad hacia arriba, no "del banquero"
        (1, "0.135", 0, "0.14"),
        (3, "10.005", 0, "30.02"),       # se redondea el subtotal, no el precio
    ],
)
def test_s5_subtotal_redondeo_mitad_hacia_arriba(cantidad, precio, pct, esperado):
    assert subtotal(cantidad, Decimal(precio), pct) == Decimal(esperado)


def test_s5_total_es_suma_de_subtotales_redondeados(datos_mini):
    r = _calc(datos_mini, [("B01", 24), ("A14", 10)])
    assert r.total == Decimal("2736.00") + Decimal("1497.60")


def test_s5_precio_es_el_del_catalogo(datos_mini):
    r = _calc(datos_mini, [("B01", 2)])
    assert r.lineas[0].precio_unitario == 120.0 and r.lineas[0].subtotal == 240.0


# ---------- §4 Agotados y sustitutos ----------

def test_s4_agotado_con_sustituto_se_entrega_el_sustituto_a_su_precio(datos_mini):
    r = _calc(datos_mini, [("A07", 3)])
    assert [(l.sku, l.cantidad, l.precio_unitario) for l in r.lineas] == [("A06", 3, 228.0)]
    assert [s.model_dump() for s in r.sustituciones] == [
        {"sku_solicitado": "A07", "sku_entregado": "A06", "cantidad": 3}
    ]
    assert r.estado is Estado.confirmado            # no requiere revisión por esto


def test_s4_descuento_del_sustituto_por_su_categoria_y_cantidad(datos_mini):
    r = _calc(datos_mini, [("A07", 10)])
    assert r.lineas[0].descuento_pct == 4


def test_s4_agotado_sin_sustituto_es_pendiente(datos_mini):
    r = _calc(datos_mini, [("S02", 2), ("B01", 1)])
    assert [l.sku for l in r.lineas] == ["B01"]
    assert [p.model_dump() for p in r.pendientes] == [
        {"motivo": Motivo.agotado_sin_sustituto, "texto": "Galletas Dulcitas Chocolate",
         "opciones": ["S02"]}
    ]
    assert r.motivos_revision == [Motivo.agotado_sin_sustituto]
    assert r.estado is Estado.requiere_revision


@pytest.mark.parametrize("sku", ["X1", "X3"])   # sustituto agotado / sustituto inexistente
def test_s4_nunca_encadena_sustituciones(datos_mini, sku):
    assert producto_a_entregar(sku, datos_mini.catalogo) is None
    r = _calc(datos_mini, [(sku, 1)])
    assert r.lineas == [] and r.sustituciones == []
    assert r.pendientes[0].motivo is Motivo.agotado_sin_sustituto


def test_s4_sustituto_pedido_tambien_directo_es_una_sola_linea(datos_mini):
    r = _calc(datos_mini, [("A06", 2), ("A07", 3)])
    assert [(l.sku, l.cantidad) for l in r.lineas] == [("A06", 5)]
    assert r.lineas[0].descuento_pct == 2        # 5 cajas de abarrotes


# ---------- §6 Crédito ----------

@pytest.mark.parametrize("total, excede", [("239.99", False), ("240.00", False), ("240.01", True)])
def test_s6_credito_borde_igual_no_excede(datos_mini, total, excede):
    # C002: límite 1000, saldo 760 → margen exacto 240
    assert credito_excedido(datos_mini.cliente("C002"), Decimal(total)) is excede


def test_s6_credito_excedido_devuelve_lineas_y_total(datos_mini):
    r = _calc(datos_mini, [("B01", 3)], cliente="C002", recibido="2026-11-23T10:00")
    assert r.estado is Estado.requiere_revision
    assert r.motivos_revision == [Motivo.credito_excedido]
    assert r.total == Decimal("360.00") and len(r.lineas) == 1
    assert r.pendientes == []                       # credito_excedido nunca va en pendientes


# ---------- §7 Fecha de entrega ----------

@pytest.mark.parametrize(
    "recibido, efectiva",
    [
        ("2026-11-23T13:59", date(2026, 11, 23)),
        ("2026-11-23T14:00", date(2026, 11, 24)),   # a las 14:00 ya cuenta como el día siguiente
        ("2026-11-23T23:59", date(2026, 11, 24)),
        ("2026-11-23T00:00", date(2026, 11, 23)),
    ],
)
def test_s7_hora_de_corte(recibido, efectiva):
    assert fecha_efectiva(datetime.fromisoformat(recibido)) == efectiva


@pytest.mark.parametrize(
    "recibido, dias, esperado",
    [
        ("2026-11-23T10:00", LUN_JUE, "2026-11-26"),  # lunes (día de visita) → jueves: POSTERIOR
        ("2026-11-22T10:00", LUN_JUE, "2026-11-23"),  # domingo → lunes
        ("2026-11-25T13:59", LUN_JUE, "2026-11-26"),  # miércoles antes del corte → jueves
        ("2026-11-25T14:00", LUN_JUE, "2026-11-30"),  # cuenta como jueves → el lunes siguiente
        ("2026-11-28T10:00", SAB, "2026-12-05"),      # sábado (visita) → sábado siguiente, cruza mes
        ("2026-12-30T15:00", LUN_JUE, "2027-01-04"),  # cruza el año
        ("2026-12-31T09:00", LUN_JUE, "2027-01-04"),
    ],
)
def test_s7_primera_visita_posterior(recibido, dias, esperado):
    assert fecha_entrega(datetime.fromisoformat(recibido), dias) == date.fromisoformat(esperado)


# ---------- §8 Estado ----------

def test_s8_confirmado(datos_mini):
    r = _calc(datos_mini, [("B01", 2)])
    assert r.estado is Estado.confirmado and r.motivos_revision == []
    assert r.fecha_entrega == date(2026, 11, 26)


def test_s8_fuera_de_alcance_sin_lineas_total_0_sin_fecha(datos_mini):
    r = _calc(datos_mini, [])
    assert r.estado is Estado.fuera_de_alcance
    assert (r.lineas, r.total, r.fecha_entrega, r.pendientes) == ([], Decimal(0), None, [])


def test_s8_solo_pendientes_requiere_revision(datos_mini):
    p = Pendiente(motivo=Motivo.producto_no_existe, texto="cerveza", opciones=[])
    r = _calc(datos_mini, [], pendientes=[p])
    assert r.estado is Estado.requiere_revision and r.lineas == []
    assert r.motivos_revision == [Motivo.producto_no_existe]


def test_s8_motivos_sin_repetir(datos_mini):
    ps = [Pendiente(motivo=Motivo.producto_no_existe, texto=t, opciones=[]) for t in ("a", "b")]
    r = _calc(datos_mini, [("B01", 1)], pendientes=ps)
    assert r.motivos_revision == [Motivo.producto_no_existe] and len(r.pendientes) == 2


@pytest.mark.parametrize(
    "items, pendientes, cliente",
    [
        ([("B01", 2)], [], "C001"),
        ([("S02", 1)], [], "C001"),
        ([("B01", 3)], [], "C002"),
        ([], [], "C001"),
        ([("A07", 2), ("S02", 1), ("B01", 30)], [], "C002"),
        ([], [Pendiente(motivo=Motivo.producto_ambiguo, texto="aceite", opciones=["A06", "A07"])],
         "C001"),
    ],
)
def test_s8_propiedad_estado(datos_mini, items, pendientes, cliente):
    """confirmado ⇔ hay líneas y motivos_revision vacío; requiere_revision ⇔ hay motivos."""
    r = _calc(datos_mini, items, pendientes, cliente=cliente)
    assert (r.estado is Estado.confirmado) == (bool(r.lineas) and not r.motivos_revision)
    assert (r.estado is Estado.requiere_revision) == bool(r.motivos_revision)
    assert Motivo.credito_excedido not in [p.motivo for p in r.pendientes]
    if r.estado is Estado.fuera_de_alcance:
        assert r.lineas == [] and r.total == 0 and r.fecha_entrega is None


# ---------- Defensa en profundidad ----------

def test_sku_fuera_del_catalogo_es_producto_no_existe(datos_mini):
    r = _calc(datos_mini, [("ZZZ9", 2), ("B01", 1)])
    assert [l.sku for l in r.lineas] == ["B01"]
    assert [(p.motivo, p.opciones) for p in r.pendientes] == [(Motivo.producto_no_existe, [])]
    assert producto_a_entregar("ZZZ9", datos_mini.catalogo) is None
