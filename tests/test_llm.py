"""Pruebas de configuración y de la fábrica del modelo. No llaman a ninguna API."""

from pathlib import Path

import pytest

from pedidos.config import Config, ErrorConfiguracion, resolver_proveedor
from pedidos.llm import OPENROUTER_BASE_URL, crear_llm, id_openrouter


def _config(proveedor: str, a_key: str = "", o_key: str = "") -> Config:
    return Config(
        proveedor=proveedor,
        anthropic_api_key=a_key,
        openrouter_api_key=o_key,
        modelo_llm="claude-haiku-5-5",
        modelo_llm_alt="claude-sonnet-5-5",
        modelo_juez="claude-opus-5-5",
        llm_timeout_s=12,
        llm_max_retries=1,
        llm_esfuerzo="low",
        ruta_datos=Path("ges"),
    )


@pytest.mark.parametrize(
    "pedido, a_key, o_key, esperado",
    [
        ("auto", "sk-ant-x", "", "anthropic"),
        ("auto", "", "sk-or-x", "openrouter"),
        ("auto", "sk-ant-x", "sk-or-x", "anthropic"),
        ("auto", "", "", "anthropic"),
        ("OpenRouter", "sk-ant-x", "", "openrouter"),
        ("", "", "sk-or-x", "openrouter"),
    ],
)
def test_resolver_proveedor(pedido, a_key, o_key, esperado):
    assert resolver_proveedor(pedido, a_key, o_key) == esperado


def test_proveedor_invalido():
    with pytest.raises(ErrorConfiguracion, match="PROVEEDOR_LLM"):
        resolver_proveedor("openai", "", "")


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("claude-haiku-5-5", "anthropic/claude-haiku-5.5"),
        ("claude-sonnet-5-5", "anthropic/claude-sonnet-5.5"),
        ("claude-opus-5", "anthropic/claude-opus-5"),
        ("anthropic/claude-haiku-5.5", "anthropic/claude-haiku-5.5"),
    ],
)
def test_id_openrouter(entrada, esperado):
    assert id_openrouter(entrada) == esperado


def test_id_openrouter_desconocido():
    with pytest.raises(ErrorConfiguracion):
        id_openrouter("gpt-x")


def test_crear_llm_anthropic():
    llm = crear_llm(config=_config("anthropic", a_key="sk-ant-prueba"))
    assert type(llm).__name__ == "ChatAnthropic"
    assert llm.model == "claude-haiku-5-5"
    assert llm.max_retries == 1


def test_crear_llm_openrouter():
    llm = crear_llm(config=_config("openrouter", o_key="sk-or-prueba"))
    assert type(llm).__name__ == "ChatOpenAI"
    assert llm.model_name == "anthropic/claude-haiku-5.5"
    assert llm.openai_api_base == OPENROUTER_BASE_URL


@pytest.mark.parametrize("proveedor, variable", [("anthropic", "ANTHROPIC"), ("openrouter", "OPENROUTER")])
def test_crear_llm_sin_clave(proveedor, variable):
    with pytest.raises(ErrorConfiguracion, match=f"Falta {variable}_API_KEY"):
        crear_llm(config=_config(proveedor))


def test_numeros_invalidos(monkeypatch):
    from pedidos.config import cargar_config

    monkeypatch.setenv("LLM_TIMEOUT_S", "rápido")
    with pytest.raises(ErrorConfiguracion, match="LLM_TIMEOUT_S"):
        cargar_config()
    monkeypatch.setenv("LLM_TIMEOUT_S", "15")
    monkeypatch.setenv("LLM_MAX_RETRIES", "-1")
    with pytest.raises(ErrorConfiguracion, match="LLM_MAX_RETRIES"):
        cargar_config()


def test_salida_estructurada_usa_json_schema():
    """Con function_calling LangChain fuerza tool_choice, que Sonnet 5.5 rechaza (400)."""
    from pydantic import BaseModel

    from pedidos.llm import METODO_ESTRUCTURADO, con_salida_estructurada

    class E(BaseModel):
        x: int

    assert METODO_ESTRUCTURADO == "json_schema"
    llm = crear_llm(config=_config("anthropic", a_key="sk-ant-prueba"))
    assert con_salida_estructurada(llm, E) is not None
