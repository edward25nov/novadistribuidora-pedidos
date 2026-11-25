"""Carga de los datos del GES (montados en RUTA_DATOS; nunca dentro del repo ni de la imagen).

Al cargar se validan las columnas mínimas de cada tabla: un archivo con otra forma falla al
arrancar con un ErrorDatos claro, nunca con un KeyError en plena solicitud.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pandas as pd

ARCHIVOS = {
    "productos": "datos/productos.parquet",
    "sinonimos": "datos/sinonimos.parquet",
    "escala": "datos/precios_escala.parquet",
    "clientes": "datos/clientes.parquet",
    "historial": "datos/historial_pedidos.parquet",
}

COLUMNAS = {
    "productos": {"sku", "nombre", "categoria", "unidad_venta", "unidades_por_empaque",
                  "precio", "disponible", "sustituto_sku"},
    "sinonimos": {"sku", "alias"},
    "escala": {"categoria", "cantidad_minima", "descuento_pct"},
    "clientes": {"cliente_id", "dias_visita", "limite_credito", "saldo_pendiente"},
    "historial": {"pedido_id", "cliente_id", "fecha_entrega", "sku", "cantidad", "estado"},
}


class ErrorDatos(RuntimeError):
    """Faltan los datos del GES o no tienen la forma esperada."""


@dataclass(frozen=True)
class Producto:
    sku: str
    nombre: str
    categoria: str
    unidad_venta: str
    unidades_por_empaque: int
    precio: Decimal
    disponible: bool
    sustituto_sku: str | None
    marca: str = ""
    presentacion: str = ""


@dataclass(frozen=True)
class Cliente:
    cliente_id: str
    dias_visita: tuple[int, ...]       # 0 = lunes … 6 = domingo
    limite_credito: Decimal
    saldo_pendiente: Decimal
    nombre_tienda: str = ""
    propietario: str = ""


_DIAS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4,
         "sabado": 5, "domingo": 6}


def _sin_tildes(texto: str) -> str:
    import unicodedata

    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def dias_de_visita(texto: str) -> tuple[int, ...]:
    """'lunes,miércoles' -> (0, 2)."""
    dias = []
    for parte in str(texto).split(","):
        nombre = _sin_tildes(parte.strip().lower())
        if not nombre:
            continue
        if nombre not in _DIAS:
            raise ErrorDatos(f"Día de visita desconocido: {parte!r}")
        dias.append(_DIAS[nombre])
    if not dias:
        raise ErrorDatos(f"El cliente no tiene días de visita: {texto!r}")
    return tuple(sorted(set(dias)))


def _texto_o_nada(v) -> str | None:
    return None if v is None or pd.isna(v) or str(v).strip() == "" else str(v).strip()


@dataclass(frozen=True)
class Datos:
    productos: pd.DataFrame
    sinonimos: pd.DataFrame
    escala: pd.DataFrame
    clientes: pd.DataFrame
    historial: pd.DataFrame
    catalogo: dict[str, Producto] = field(init=False, repr=False)
    _clientes: dict[str, Cliente] = field(init=False, repr=False)

    def __post_init__(self):
        for nombre, requeridas in COLUMNAS.items():
            faltan = requeridas - set(getattr(self, nombre).columns)
            if faltan:
                raise ErrorDatos(
                    f"La tabla {nombre} ({ARCHIVOS[nombre]}) no tiene las columnas "
                    f"{sorted(faltan)}."
                )
        catalogo = {}
        for r in self.productos.to_dict("records"):
            upe = int(r["unidades_por_empaque"])
            if upe < 1:
                raise ErrorDatos(f"{r['sku']}: unidades_por_empaque debe ser >= 1")
            catalogo[str(r["sku"])] = Producto(
                sku=str(r["sku"]), nombre=str(r["nombre"]), categoria=str(r["categoria"]),
                unidad_venta=str(r["unidad_venta"]), unidades_por_empaque=upe,
                precio=Decimal(str(r["precio"])), disponible=bool(r["disponible"]),
                sustituto_sku=_texto_o_nada(r["sustituto_sku"]),
                marca=str(r.get("marca") or ""), presentacion=str(r.get("presentacion") or ""),
            )
        clientes = {}
        for r in self.clientes.to_dict("records"):
            clientes[str(r["cliente_id"])] = Cliente(
                cliente_id=str(r["cliente_id"]), dias_visita=dias_de_visita(r["dias_visita"]),
                limite_credito=Decimal(str(r["limite_credito"])),
                saldo_pendiente=Decimal(str(r["saldo_pendiente"])),
                nombre_tienda=str(r.get("nombre_tienda") or ""),
                propietario=str(r.get("propietario") or ""),
            )
        object.__setattr__(self, "catalogo", catalogo)
        object.__setattr__(self, "_clientes", clientes)

    def existe_cliente(self, cliente_id: str) -> bool:
        return cliente_id in self._clientes

    def cliente(self, cliente_id: str) -> Cliente:
        return self._clientes[cliente_id]

    def ultimo_pedido_entregado(self, cliente_id: str) -> list[tuple[str, int]]:
        """Líneas (sku, cantidad) del último pedido con estado 'entregado' (política §3).
        Los cancelados no cuentan. Lista vacía si el cliente no tiene ninguno."""
        h = self.historial
        h = h[(h["cliente_id"] == cliente_id) & (h["estado"] == "entregado")]
        if h.empty:
            return []
        ultima = h["fecha_entrega"].max()
        ultimos = h[h["fecha_entrega"] == ultima]
        pedido = sorted(ultimos["pedido_id"].unique())[-1]
        lineas = h[h["pedido_id"] == pedido]
        return [(str(r["sku"]), int(r["cantidad"])) for r in lineas.to_dict("records")]


def cargar_datos(ruta: Path) -> Datos:
    ruta = Path(ruta).resolve()
    faltan = [rel for rel in ARCHIVOS.values() if not (ruta / rel).is_file()]
    if faltan:
        raise ErrorDatos(
            f"No encuentro los datos del GES en {ruta} (faltan: {', '.join(faltan)}). "
            "Descomprima el archivo del GES en la carpeta ges/ del repositorio "
            "(ver README, sección 1) o ajuste RUTA_DATOS."
        )
    try:
        tablas = {nombre: pd.read_parquet(ruta / rel) for nombre, rel in ARCHIVOS.items()}
    except Exception as e:   # archivo corrupto o con otro formato
        raise ErrorDatos(f"No pude leer los datos del GES en {ruta}: {e}") from e
    return Datos(**tablas)
