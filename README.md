# NovaDistribuidora · Toma de pedidos por WhatsApp

Aplicación con LLMs (LangChain + FastAPI + MLflow + Docker) que convierte mensajes informales
de WhatsApp en pedidos estructurados y verificables. Laboratorio 3 de Product Development.

> En construcción: este README se completa fase a fase.

## 1. Datos del GES

Los datos no forman parte del repositorio. Descomprima el archivo publicado en el GES en la
carpeta `ges/` de la raíz del repositorio:

```bash
unzip lab3.zip -d ges
# ges/datos/*.parquet, ges/ejemplos/mensajes_dev.jsonl, ges/politicas.md, ges/catalogo_problemas.md
```

## 2. Credenciales

```bash
cp .env.example .env
```

Ponga **una** de las dos claves en `.env`:

| Clave | Proveedor que se usa (con `PROVEEDOR_LLM=auto`) |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter, modelo `anthropic/claude-haiku-5.5` |
| `ANTHROPIC_API_KEY` | API de Anthropic, modelo `claude-haiku-5-5` |

El modelo es `MODELO_LLM` (`claude-haiku-5-5`); con OpenRouter el id se traduce solo.

## 3. Desarrollo local

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest
```
