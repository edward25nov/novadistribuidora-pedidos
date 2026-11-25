"""Carga de los datos del GES (montados en RUTA_DATOS; nunca dentro del repo ni de la imagen)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ARCHIVOS = {
    "productos": "datos/productos.parquet",
    "sinonimos": "datos/sinonimos.parquet",
    "escala": "datos/precios_escala.parquet",
    "clientes": "datos/clientes.parquet",
    "historial": "datos/historial_pedidos.parquet",
}


class ErrorDatos(RuntimeError):
    """Faltan los datos del GES o no tienen la forma esperada."""


@dataclass(frozen=True)
class Datos:
    productos: pd.DataFrame
    sinonimos: pd.DataFrame
    escala: pd.DataFrame
    clientes: pd.DataFrame
    historial: pd.DataFrame

    def existe_cliente(self, cliente_id: str) -> bool:
        return bool((self.clientes["cliente_id"] == cliente_id).any())


def cargar_datos(ruta: Path) -> Datos:
    ruta = Path(ruta).resolve()
    faltan = [rel for rel in ARCHIVOS.values() if not (ruta / rel).is_file()]
    if faltan:
        raise ErrorDatos(
            f"No encuentro los datos del GES en {ruta} (faltan: {', '.join(faltan)}). "
            "Descomprima el archivo del GES en la carpeta ges/ del repositorio "
            "(ver README, sección 1) o ajuste RUTA_DATOS."
        )
    tablas = {nombre: pd.read_parquet(ruta / rel) for nombre, rel in ARCHIVOS.items()}
    return Datos(**tablas)
