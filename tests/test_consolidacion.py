"""Cantidades, conversión de unidades y 'lo de siempre' (politicas.md §2 y §3)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from pedidos.consolidacion import (
    Accion, MencionHabitual, MencionResuelta as M, TipoUnidad as U, a_unidades_de_venta,
    consolidar,
)
from pedidos.esquemas import Motivo


def _items(datos, menciones, cliente="C001"):
    items, pendientes = consolidar(menciones, datos, cliente)
    return [(i.sku, i.cantidad) for i in items], pendientes


# ---------- §2 Cantidades ----------

def test_s2_sin_unidad_es_unidad_de_venta(datos_mini):
    assert _items(datos_mini, [M("3 de kola 600", "B01", Decimal(3))])[0] == [("B01", 3)]


def test_s2_sin_cantidad_es_1(datos_mini):
    assert _items(datos_mini, [M("y unas kolas", "B01")])[0] == [("B01", 1)]


@pytest.mark.parametrize(
    "cantidad, unidad, sku, esperado",
    [
        (48, U.suelta, "B01", 2),        # 48 latas / 24
        (72, U.suelta, "B01", 3),
        (1, U.docena, "L03", 1),         # una docena de cloro (caja de 12)
        (2, U.docena, "B01", 1),         # 24 botellas
        (5, U.empaque, "A02", 5),        # quintal
    ],
)
def test_s2_conversion_exacta(datos_mini, cantidad, unidad, sku, esperado):
    assert _items(datos_mini, [M("x", sku, Decimal(cantidad), unidad)])[0] == [(sku, esperado)]


@pytest.mark.parametrize(
    "cantidad, unidad, sku",
    [
        (36, U.suelta, "B01"),           # 36 botellas de un fardo de 24: no se redondea
        (1, U.docena, "B01"),            # 12 de 24
        (Decimal("0.5"), U.empaque, "A02"),   # medio quintal
        (0, U.empaque, "B01"),
    ],
)
def test_s2_conversion_no_exacta_es_pendiente(datos_mini, cantidad, unidad, sku):
    items, pendientes = _items(datos_mini, [M("36 botellas de kola", sku, Decimal(cantidad), unidad)])
    assert items == []
    assert [(p.motivo, p.opciones) for p in pendientes] == [
        (Motivo.cantidad_no_convertible, [sku])
    ]


def test_s2_menciones_repetidas_se_suman(datos_mini):
    ms = [M("2 fardos de kola", "B01", Decimal(2), U.empaque),
          M("y otros 3 de kola", "B01", Decimal(3))]
    assert _items(datos_mini, ms)[0] == [("B01", 5)]


def test_s2_se_suma_antes_de_convertir(datos_mini):
    ms = [M("12 latas", "B01", Decimal(12), U.suelta), M("12 latas más", "B01", Decimal(12), U.suelta)]
    assert _items(datos_mini, ms)[0] == [("B01", 1)]


def test_s2_correccion_reemplaza(datos_mini):
    ms = [M("3 fardos de kola 600", "B01", Decimal(3), U.empaque),
          M("no, mejor que sean 5", "B01", Decimal(5), accion=Accion.corregir)]
    assert _items(datos_mini, ms)[0] == [("B01", 5)]


def test_s2_correccion_de_cantidad_no_convertible_la_vuelve_valida(datos_mini):
    ms = [M("36 botellas", "B01", Decimal(36), U.suelta),
          M("no, que sean 48", "B01", Decimal(48), U.suelta, Accion.corregir)]
    items, pendientes = _items(datos_mini, ms)
    assert items == [("B01", 2)] and pendientes == []


def test_s2_quitar_elimina_la_linea(datos_mini):
    ms = [M("2 kola", "B01", Decimal(2)), M("1 aceite", "A06", Decimal(1)),
          M("pero sin la kola", "B01", accion=Accion.quitar)]
    assert _items(datos_mini, ms)[0] == [("A06", 1)]


def test_s2_orden_de_primera_aparicion(datos_mini):
    ms = [M("a", "A06", Decimal(1)), M("b", "B01", Decimal(1)), M("c", "A06", Decimal(1))]
    assert _items(datos_mini, ms)[0] == [("A06", 2), ("B01", 1)]


def test_a_unidades_de_venta():
    assert a_unidades_de_venta(Decimal(48), 24) == 2
    assert a_unidades_de_venta(Decimal(36), 24) is None
    assert a_unidades_de_venta(Decimal(-24), 24) is None


# ---------- §3 "Lo de siempre" ----------

def test_s3_ultimo_pedido_entregado_ignora_cancelados(datos_mini):
    assert datos_mini.ultimo_pedido_entregado("C001") == [("B01", 2), ("A07", 1), ("S02", 3)]


def test_s3_lo_de_siempre_con_agregado_y_exclusion(datos_mini):
    ms = [MencionHabitual("lo de siempre"), M("y 2 kola", "B01", Decimal(2)),
          M("pero sin galletas", "S02", accion=Accion.quitar), M("1 nutrimezcla", "A14", Decimal(1))]
    assert _items(datos_mini, ms)[0] == [("B01", 4), ("A07", 1), ("A14", 1)]


def test_s3_sin_pedido_entregado_es_pendiente(datos_mini):
    items, pendientes = _items(datos_mini, [MencionHabitual("lo de siempre")], cliente="C002")
    assert items == []
    assert [(p.motivo, p.texto, p.opciones) for p in pendientes] == [
        (Motivo.producto_ambiguo, "lo de siempre", [])
    ]


def test_sku_fuera_del_catalogo_es_pendiente(datos_mini):
    items, pendientes = _items(datos_mini, [M("2 cervezas", "ZZZ9", Decimal(2))])
    assert items == [] and [(p.motivo, p.texto) for p in pendientes] == [
        (Motivo.producto_no_existe, "2 cervezas")
    ]


def test_s3_sku_historico_fuera_del_catalogo_es_pendiente(datos_mini):
    import pandas as pd

    from pedidos.datos import Datos

    h = datos_mini.historial.copy()
    h.loc[len(h)] = ["PED-9", "C003", pd.Timestamp("2026-11-20"), "VIEJO", 2, "entregado"]
    d = Datos(productos=datos_mini.productos, sinonimos=datos_mini.sinonimos,
              escala=datos_mini.escala, clientes=datos_mini.clientes, historial=h)
    items, pendientes = _items(d, [MencionHabitual("lo de siempre")], cliente="C003")
    assert items == [] and pendientes[0].motivo is Motivo.producto_no_existe
    assert "VIEJO" in pendientes[0].texto


def test_s8_quitar_todo_queda_fuera_de_alcance(datos_mini):
    from datetime import datetime

    from pedidos.esquemas import Estado
    from pedidos.reglas import calcular_pedido

    ms = [M("2 kola", "B01", Decimal(2)), M("mejor no, quíteme la kola", "B01", accion=Accion.quitar)]
    items, pendientes = consolidar(ms, datos_mini, "C001")
    r = calcular_pedido("C001", datetime(2026, 11, 23, 10), items, pendientes, datos_mini)
    assert r.estado is Estado.fuera_de_alcance and r.total == 0 and r.fecha_entrega is None
