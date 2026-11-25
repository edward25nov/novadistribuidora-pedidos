"""Contrato del servicio (Anexo del enunciado): solicitud y respuesta de la API."""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_MENSAJES = 20
MAX_CARACTERES_MENSAJE = 2000
_FORMATO_FECHA_HORA = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")


class Estado(str, Enum):
    confirmado = "confirmado"
    requiere_revision = "requiere_revision"
    fuera_de_alcance = "fuera_de_alcance"


class Motivo(str, Enum):
    producto_ambiguo = "producto_ambiguo"
    producto_no_existe = "producto_no_existe"
    agotado_sin_sustituto = "agotado_sin_sustituto"
    cantidad_no_convertible = "cantidad_no_convertible"
    credito_excedido = "credito_excedido"   # solo en motivos_revision, nunca en pendientes


MOTIVOS_PENDIENTE = tuple(m for m in Motivo if m is not Motivo.credito_excedido)


# ---------- Solicitud ----------

class SolicitudPedido(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cliente_id: str = Field(min_length=1, max_length=20)
    fecha_hora: str = Field(description="AAAA-MM-DDTHH:MM, hora de Guatemala")
    mensajes: list[str] = Field(min_length=1, max_length=MAX_MENSAJES)

    @field_validator("cliente_id")
    @classmethod
    def _cliente(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("cliente_id no puede estar vacío")
        return v

    @field_validator("fecha_hora")
    @classmethod
    def _fecha_hora(cls, v: str) -> str:
        v = v.strip()
        if not _FORMATO_FECHA_HORA.match(v):
            raise ValueError("fecha_hora debe tener el formato AAAA-MM-DDTHH:MM")
        try:
            datetime.strptime(v, "%Y-%m-%dT%H:%M")
        except ValueError:
            raise ValueError("fecha_hora no es una fecha y hora válida") from None
        return v

    @field_validator("mensajes")
    @classmethod
    def _mensajes(cls, v: list[str]) -> list[str]:
        for i, m in enumerate(v):
            if not m.strip():
                raise ValueError(f"el mensaje {i} está vacío")
            if len(m) > MAX_CARACTERES_MENSAJE:
                raise ValueError(
                    f"el mensaje {i} supera {MAX_CARACTERES_MENSAJE} caracteres"
                )
        return v

    @property
    def recibido(self) -> datetime:
        """Hora local de Guatemala, sin zona: no se convierte."""
        return datetime.strptime(self.fecha_hora, "%Y-%m-%dT%H:%M")


# ---------- Respuesta ----------

class Linea(BaseModel):
    sku: str
    cantidad: int = Field(gt=0)
    precio_unitario: float
    descuento_pct: int = Field(ge=0, le=100)
    subtotal: float


class Sustitucion(BaseModel):
    sku_solicitado: str
    sku_entregado: str
    cantidad: int = Field(gt=0)


class Pendiente(BaseModel):
    motivo: Motivo
    texto: str
    opciones: list[str] = Field(default_factory=list)

    @field_validator("motivo")
    @classmethod
    def _no_credito(cls, v: Motivo) -> Motivo:
        if v is Motivo.credito_excedido:
            raise ValueError("credito_excedido solo va en motivos_revision")
        return v


class RespuestaPedido(BaseModel):
    cliente_id: str
    estado: Estado
    lineas: list[Linea]
    total: float
    fecha_entrega: date | None
    sustituciones: list[Sustitucion]
    pendientes: list[Pendiente]
    motivos_revision: list[Motivo]
    mensaje_cliente: str


class Salud(BaseModel):
    estado: str                         # "ok" | "degradado"
    motivo: str | None = None           # presente solo si está degradado
    dependencias: dict[str, str]        # p. ej. {"mlflow": "ok", "datos": "ok", "llm": "ok"}
