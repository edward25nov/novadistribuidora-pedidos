"""Único lugar donde se crea el modelo de lenguaje.

Proveedores:
- anthropic: ChatAnthropic, directo a la API de Anthropic (lo que usamos en desarrollo).
- openrouter: ChatOpenAI contra la API compatible con OpenAI de OpenRouter (lo que pide
  el enunciado; el equipo docente evalúa con su propia clave de OpenRouter).

Sin `temperature`: los modelos actuales de Claude la rechazan.
"""

from __future__ import annotations

import re

from langchain_core.language_models.chat_models import BaseChatModel

from pedidos.config import Config, ErrorConfiguracion, cargar_config

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_ID_ANTHROPIC = re.compile(r"^(claude-[a-z]+)-(\d+)(?:-(\d+))?$")


def id_openrouter(modelo: str) -> str:
    """Traduce un id de Anthropic al de OpenRouter.

    claude-haiku-5-5 -> anthropic/claude-haiku-5.5 ; claude-opus-5 -> anthropic/claude-opus-5.
    Un id que ya trae "/" se deja tal cual.
    """
    if "/" in modelo:
        return modelo
    m = _ID_ANTHROPIC.match(modelo)
    if not m:
        raise ErrorConfiguracion(f"No sé traducir el modelo {modelo!r} a un id de OpenRouter.")
    familia, mayor, menor = m.groups()
    version = f"{mayor}.{menor}" if menor else mayor
    return f"anthropic/{familia}-{version}"


def crear_llm(modelo: str | None = None, config: Config | None = None) -> BaseChatModel:
    """Crea el modelo del proveedor configurado. `modelo` por defecto es MODELO_LLM."""
    config = config or cargar_config()
    nombre = modelo or config.modelo_llm
    if not config.api_key:
        variable = "ANTHROPIC_API_KEY" if config.proveedor == "anthropic" else "OPENROUTER_API_KEY"
        raise ErrorConfiguracion(f"Falta {variable} en el .env (proveedor {config.proveedor}).")

    if config.proveedor == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=nombre,
            api_key=config.api_key,
            max_tokens=2048,
            timeout=config.llm_timeout_s,
            max_retries=config.llm_max_retries,
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=id_openrouter(nombre),
        api_key=config.api_key,
        base_url=OPENROUTER_BASE_URL,
        max_tokens=2048,
        timeout=config.llm_timeout_s,
        max_retries=config.llm_max_retries,
    )
