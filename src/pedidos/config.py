"""Configuración leída de variables de entorno (.env). Ningún secreto va en el código."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROVEEDORES = ("anthropic", "openrouter")


class ErrorConfiguracion(RuntimeError):
    """La configuración no permite arrancar o llamar al modelo."""


@dataclass(frozen=True)
class Config:
    proveedor: str                 # "anthropic" | "openrouter" (ya resuelto, nunca "auto")
    anthropic_api_key: str
    openrouter_api_key: str
    modelo_llm: str
    modelo_llm_alt: str
    modelo_juez: str
    llm_timeout_s: float
    llm_max_retries: int
    ruta_datos: Path

    @property
    def api_key(self) -> str:
        return self.anthropic_api_key if self.proveedor == "anthropic" else self.openrouter_api_key


def resolver_proveedor(pedido: str, anthropic_key: str, openrouter_key: str) -> str:
    """auto: Anthropic si hay su clave; si no, OpenRouter; si no hay ninguna, Anthropic
    (el /health avisará que falta la clave)."""
    pedido = (pedido or "auto").strip().lower()
    if pedido in PROVEEDORES:
        return pedido
    if pedido != "auto":
        raise ErrorConfiguracion(
            f"PROVEEDOR_LLM={pedido!r} no es válido; use anthropic, openrouter o auto."
        )
    if anthropic_key:
        return "anthropic"
    if openrouter_key:
        return "openrouter"
    return "anthropic"


def cargar_config() -> Config:
    a_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    o_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    return Config(
        proveedor=resolver_proveedor(os.getenv("PROVEEDOR_LLM", "auto"), a_key, o_key),
        anthropic_api_key=a_key,
        openrouter_api_key=o_key,
        modelo_llm=os.getenv("MODELO_LLM", "claude-haiku-5-5"),
        modelo_llm_alt=os.getenv("MODELO_LLM_ALT", "claude-sonnet-5-5"),
        modelo_juez=os.getenv("MODELO_JUEZ", "claude-opus-5-5"),
        llm_timeout_s=float(os.getenv("LLM_TIMEOUT_S", "30")),
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "1")),
        ruta_datos=Path(os.getenv("RUTA_DATOS", "./ges")),
    )
