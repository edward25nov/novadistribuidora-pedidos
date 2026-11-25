"""Mensaje al cliente (politicas.md §9) armado desde el pedido calculado."""

from __future__ import annotations

from datetime import datetime

from pedidos.confirmacion import cantidad_con_unidad, redactar, saludo
from pedidos.consolidacion import ItemPedido
from pedidos.esquemas import Motivo, Pendiente
from pedidos.reglas import calcular_pedido

TARDE = datetime(2026, 11, 23, 15, 20)


def _pedido(datos, items, pendientes=(), cliente="C001", recibido=TARDE):
    return calcular_pedido(cliente, recibido, [ItemPedido(s, c, s) for s, c in items],
                           list(pendientes), datos)


def test_saludo_por_hora():
    assert saludo(datetime(2026, 1, 1, 9)) == "¡Buenos días!"
    assert saludo(datetime(2026, 1, 1, 15)) == "¡Buenas tardes!"
    assert saludo(datetime(2026, 1, 1, 20)) == "¡Buenas noches!"


def test_plurales():
    assert cantidad_con_unidad(1, "fardo") == "1 fardo"
    assert cantidad_con_unidad(2, "quintal") == "2 quintales"
    assert cantidad_con_unidad(3, "display") == "3 displays"


def test_s9_confirmado_con_lineas_total_y_fecha(datos_mini):
    m = redactar(_pedido(datos_mini, [("B01", 2)]), datos_mini, TARDE)
    assert m.startswith("¡Buenas tardes!")
    assert "2 fardos de Kola Norte 600 ml" in m
    assert "Q240.00" in m
    assert "jueves 26 de noviembre" in m


def test_s9_no_promete_agotados_ni_pendientes(datos_mini):
    amb = Pendiente(motivo=Motivo.producto_ambiguo, texto="aceite", opciones=["A06", "A07"])
    m = redactar(_pedido(datos_mini, [("B01", 1), ("S02", 2)], [amb]), datos_mini, TARDE)
    assert "«Galletas Dulcitas Chocolate»" in m and "«aceite»" in m
    assert "un asesor le confirmará" in m
    assert "Recibimos su pedido: 1 fardo de Kola Norte 600 ml." in m   # solo lo que va


def test_s9_sustitucion_explicada(datos_mini):
    m = redactar(_pedido(datos_mini, [("A07", 2)]), datos_mini, TARDE)
    assert "2 cajas de Aceite Girasol Dorado 750 ml" in m
    assert "Aceite Palma Real 750 ml está agotado; en su lugar le enviamos" in m


def test_s9_credito_dice_que_un_asesor_confirmara(datos_mini):
    m = redactar(_pedido(datos_mini, [("B01", 3)], cliente="C002"), datos_mini, TARDE)
    assert "límite de crédito" in m and "Entrega prevista" in m


def test_s9_total_del_mensaje_es_el_calculado(datos_mini):
    p = _pedido(datos_mini, [("B01", 24), ("A14", 10)])
    assert f"Q{p.total:,.2f}" in redactar(p, datos_mini, TARDE)


def test_s9_fuera_de_alcance(datos_mini):
    m = redactar(_pedido(datos_mini, []), datos_mini, datetime(2026, 1, 1, 8))
    assert m.startswith("¡Buenos días!") and "asesor" in m and "Q" not in m
