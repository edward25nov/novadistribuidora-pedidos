"""Datos sintéticos mínimos: las pruebas no dependen de los archivos del GES ni del modelo."""

from __future__ import annotations

import pandas as pd
import pytest

from pedidos.datos import Datos


@pytest.fixture
def datos_mini() -> Datos:
    return Datos(
        productos=pd.DataFrame(
            [
                {"sku": "B01", "nombre": "Kola Norte 600 ml", "marca": "Kola Norte",
                 "categoria": "bebidas", "presentacion": "600 ml", "unidad_venta": "fardo",
                 "unidades_por_empaque": 24, "precio": 120.0, "disponible": True,
                 "sustituto_sku": None},
            ]
        ),
        sinonimos=pd.DataFrame([{"sku": "B01", "alias": "kola 600"}]),
        escala=pd.DataFrame([{"categoria": "bebidas", "cantidad_minima": 10, "descuento_pct": 3}]),
        clientes=pd.DataFrame(
            [
                {"cliente_id": "C001", "nombre_tienda": "Tienda", "propietario": "X",
                 "municipio": "Mixco", "dias_visita": "lunes,jueves",
                 "limite_credito": 8000, "saldo_pendiente": 1200},
            ]
        ),
        historial=pd.DataFrame(
            columns=["pedido_id", "cliente_id", "fecha_entrega", "sku", "cantidad", "estado"]
        ),
    )
