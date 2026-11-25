"""Carga y validación de los datos del GES (con datos sintéticos)."""

from __future__ import annotations

import pytest

from conftest import construir_datos
from pedidos.datos import Datos, ErrorDatos, cargar_datos, dias_de_visita


def test_columnas_faltantes_dan_error_claro():
    d = construir_datos()
    with pytest.raises(ErrorDatos, match=r"productos .*precio"):
        Datos(productos=d.productos.drop(columns=["precio"]), sinonimos=d.sinonimos,
              escala=d.escala, clientes=d.clientes, historial=d.historial)


def test_catalogo_tipado(datos_mini):
    p = datos_mini.catalogo["A07"]
    assert (p.disponible, p.sustituto_sku, str(p.precio)) == (False, "A06", "192.0")
    assert datos_mini.catalogo["S02"].sustituto_sku is None


@pytest.mark.parametrize(
    "texto, esperado",
    [("lunes,jueves", (0, 3)), ("miércoles,sábado", (2, 5)), ("Sábado", (5,)),
     ("lunes, miercoles ,viernes", (0, 2, 4))],
)
def test_dias_de_visita(texto, esperado):
    assert dias_de_visita(texto) == esperado


def test_dia_desconocido():
    with pytest.raises(ErrorDatos):
        dias_de_visita("lunes,feriado")


def test_carpeta_inexistente_menciona_ruta_y_readme(tmp_path):
    with pytest.raises(ErrorDatos, match="README") as e:
        cargar_datos(tmp_path / "nada")
    assert str(tmp_path / "nada") in str(e.value)
