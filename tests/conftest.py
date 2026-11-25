"""Datos sintéticos mínimos: las pruebas no dependen de los archivos del GES ni del modelo."""

from __future__ import annotations

import pandas as pd
import pytest

from pedidos.datos import Datos


def _p(sku, nombre, categoria, unidad, upe, precio, disponible=True, sustituto=None):
    return {"sku": sku, "nombre": nombre, "marca": nombre.split()[0], "categoria": categoria,
            "presentacion": "", "unidad_venta": unidad, "unidades_por_empaque": upe,
            "precio": precio, "disponible": disponible, "sustituto_sku": sustituto}


PRODUCTOS = [
    _p("B01", "Kola Norte 600 ml", "bebidas", "fardo", 24, 120.0),
    _p("B02", "Kola Norte 1.5 L", "bebidas", "fardo", 12, 144.0),
    _p("B03", "Kola Norte 3 L", "bebidas", "fardo", 6, 132.0, False, "B02"),
    _p("A02", "Arroz La Ceiba quintal", "abarrotes", "quintal", 1, 480.0),
    _p("A06", "Aceite Girasol Dorado 750 ml", "abarrotes", "caja", 12, 228.0),
    _p("A07", "Aceite Palma Real 750 ml", "abarrotes", "caja", 12, 192.0, False, "A06"),
    _p("A14", "Nutrimezcla 450 g", "abarrotes", "caja", 12, 156.0),
    _p("S02", "Galletas Dulcitas Chocolate", "snacks", "display", 12, 48.0, False),
    _p("X1", "Producto X1", "snacks", "display", 10, 10.0, False, "X2"),   # sustituto agotado
    _p("X2", "Producto X2", "snacks", "display", 10, 12.0, False),
    _p("X3", "Producto X3", "snacks", "display", 10, 10.0, False, "NO-EXISTE"),
    _p("L03", "Cloro Blancura 1 L", "limpieza", "caja", 12, 108.0),
]

ESCALA = [
    {"categoria": "bebidas", "cantidad_minima": 10, "descuento_pct": 3},
    {"categoria": "bebidas", "cantidad_minima": 20, "descuento_pct": 5},
    {"categoria": "abarrotes", "cantidad_minima": 5, "descuento_pct": 2},
    {"categoria": "abarrotes", "cantidad_minima": 10, "descuento_pct": 4},
]

CLIENTES = [
    {"cliente_id": "C001", "nombre_tienda": "Tienda La Bendición", "propietario": "Marta",
     "municipio": "Mixco", "dias_visita": "lunes,jueves", "limite_credito": 8000,
     "saldo_pendiente": 1200},
    {"cliente_id": "C002", "nombre_tienda": "Don Chema", "propietario": "José",
     "municipio": "Z6", "dias_visita": "miércoles,sábado", "limite_credito": 1000,
     "saldo_pendiente": 760},
    {"cliente_id": "C003", "nombre_tienda": "Nueva", "propietario": "Ana",
     "municipio": "VN", "dias_visita": "sábado", "limite_credito": 5000, "saldo_pendiente": 0},
]

HISTORIAL = [
    # C001: el último ENTREGADO es PED-2 (PED-3 es más reciente pero cancelado)
    ("PED-1", "C001", "2026-11-02", "B01", 5, "entregado"),
    ("PED-2", "C001", "2026-11-09", "B01", 2, "entregado"),
    ("PED-2", "C001", "2026-11-09", "A07", 1, "entregado"),
    ("PED-2", "C001", "2026-11-09", "S02", 3, "entregado"),
    ("PED-3", "C001", "2026-11-16", "A02", 9, "cancelado"),
    # C002: solo cancelados → no hay "lo de siempre"
    ("PED-4", "C002", "2026-11-10", "B01", 1, "cancelado"),
]


def construir_datos() -> Datos:
    hist = pd.DataFrame(HISTORIAL, columns=["pedido_id", "cliente_id", "fecha_entrega", "sku",
                                            "cantidad", "estado"])
    hist["fecha_entrega"] = pd.to_datetime(hist["fecha_entrega"])
    return Datos(
        productos=pd.DataFrame(PRODUCTOS),
        sinonimos=pd.DataFrame([{"sku": "B01", "alias": "kola 600"}]),
        escala=pd.DataFrame(ESCALA),
        clientes=pd.DataFrame(CLIENTES),
        historial=hist,
    )


@pytest.fixture
def datos_mini() -> Datos:
    return construir_datos()
