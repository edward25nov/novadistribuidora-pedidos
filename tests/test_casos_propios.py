"""Los casos propios tienen exactamente el formato de mensajes_dev.jsonl."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pedidos.esquemas import Estado, Motivo, SolicitudPedido

RAIZ = Path(__file__).resolve().parents[1]
PROPIOS = RAIZ / "ejemplos" / "casos_propios.jsonl"
DEV = RAIZ / "ges" / "ejemplos" / "mensajes_dev.jsonl"
CLAVES = {"id", "tipo", "entrada", "esperado"}
CLAVES_ESPERADO = {"estado", "lineas", "total", "fecha_entrega", "sustituciones", "pendientes",
                   "motivos_revision"}
CLAVES_LINEA = {"sku", "cantidad", "precio_unitario", "descuento_pct", "subtotal"}


def _casos(ruta):
    return [json.loads(l) for l in ruta.read_text().splitlines() if l.strip()]


def test_formato_de_los_casos_propios():
    casos = _casos(PROPIOS)
    assert len(casos) >= 30
    assert len({c["id"] for c in casos}) == len(casos)
    for c in casos:
        assert set(c) == CLAVES, c["id"]
        SolicitudPedido(**c["entrada"])                       # entrada válida para la API
        e = c["esperado"]
        assert set(e) == CLAVES_ESPERADO, c["id"]
        Estado(e["estado"])
        assert all(set(l) == CLAVES_LINEA for l in e["lineas"])
        assert all(set(p) == {"motivo", "texto", "opciones"} for p in e["pendientes"])
        assert all(Motivo(m) for m in e["motivos_revision"])
        if e["estado"] == "fuera_de_alcance":
            assert e["lineas"] == [] and e["total"] == 0 and e["fecha_entrega"] is None


@pytest.mark.skipif(not DEV.is_file(), reason="datos del GES no disponibles")
def test_mismo_formato_que_los_casos_publicados():
    dev, propios = _casos(DEV)[0], _casos(PROPIOS)[0]
    assert set(dev) == set(propios)
    assert set(dev["esperado"]) == set(propios["esperado"])
    assert set(dev["entrada"]) == set(propios["entrada"])


@pytest.mark.skipif(not DEV.is_file(), reason="datos del GES no disponibles")
def test_el_archivo_es_el_que_genera_el_script():
    import sys

    sys.path.insert(0, str(RAIZ / "scripts"))
    from generar_casos_propios import generar

    assert generar(RAIZ / "ges") == _casos(PROPIOS)
