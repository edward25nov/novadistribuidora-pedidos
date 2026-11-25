"""Único lugar donde se crea el modelo de lenguaje.

Proveedores:
- anthropic: ChatAnthropic, directo a la API de Anthropic (lo que usamos en desarrollo).
- openrouter: ChatOpenAI contra la API compatible con OpenAI de OpenRouter (lo que pide
  el enunciado; el equipo docente evalúa con su propia clave de OpenRouter).

Decisiones (ver DECISIONES.md D1, D4, D5):
- No se envía `temperature`: Claude Haiku 5.5 y Sonnet 5.5 responden 400 a valores distintos
  del predeterminado, así que lo dejamos en el valor del proveedor.
- Salida estructurada con `method="json_schema"` (salida estructurada nativa). Con
  "function_calling" LangChain fuerza `tool_choice`, que Sonnet 5.5 rechaza con 400.
"""

from __future__ import annotations

import re

from langchain_core.language_models.chat_models import BaseChatModel

from pedidos.config import Config, ErrorConfiguracion, cargar_config

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# OpenRouter reparte las solicitudes entre proveedores (Anthropic, Bedrock, Vertex…) y la caché
# de prompt es por proveedor: sin fijar el orden, cada llamada escribía la caché y no la leía.
# Preferimos Anthropic y permitimos respaldo si no está disponible (D5).
OPENROUTER_PROVEEDORES = {"provider": {"order": ["anthropic"], "allow_fallbacks": True}}
METODO_ESTRUCTURADO = "json_schema"

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
        raise ErrorConfiguracion(
            f"Falta {config.variable_api_key} en el .env (proveedor {config.proveedor})."
        )

    if config.proveedor == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=nombre,
            api_key=config.api_key,
            max_tokens=4096,
            timeout=config.llm_timeout_s,
            max_retries=config.llm_max_retries,
            reasoning_effort=config.llm_esfuerzo,
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=id_openrouter(nombre),
        api_key=config.api_key,
        base_url=OPENROUTER_BASE_URL,
        max_tokens=4096,
        timeout=config.llm_timeout_s,
        max_retries=config.llm_max_retries,
        reasoning_effort=config.llm_esfuerzo,
        extra_body=OPENROUTER_PROVEEDORES,
    )


def con_salida_estructurada(llm: BaseChatModel, esquema: type, incluir_crudo: bool = True):
    """Envuelve el modelo para que devuelva una instancia de `esquema` (Pydantic).

    Con `include_raw=True` se conserva el mensaje crudo (uso de tokens para costo) y el error
    de parseo en vez de lanzar excepción: el servicio decide qué hacer.
    """
    return llm.with_structured_output(
        esquema, method=METODO_ESTRUCTURADO, include_raw=incluir_crudo
    )
