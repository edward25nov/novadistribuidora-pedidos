# Decisiones

Cada decisión registra sus alternativas y su justificación. Las que dependen de mediciones se
actualizan con los números de la evaluación (fase 6).

## D1. Proveedor del modelo: Anthropic directo, con OpenRouter seleccionable

- **Contexto:** el enunciado pide OpenRouter; en el curso trabajamos con la API de Anthropic
  (clase 6). El equipo docente evaluará con **su** clave de OpenRouter y el modelo de `.env.example`.
- **Alternativas:** (a) solo OpenRouter; (b) solo Anthropic; (c) proveedor por variable.
- **Decisión:** (c). `PROVEEDOR_LLM=anthropic|openrouter|auto` en `.env`; con `auto` se usa
  Anthropic si `ANTHROPIC_API_KEY` tiene valor y, si no, OpenRouter. Una sola fábrica
  (`crear_llm` en `src/pedidos/llm.py`): `ChatAnthropic` o `ChatOpenAI` con
  `base_url=https://openrouter.ai/api/v1`.
- **Por qué:** desarrollamos y medimos con Anthropic, pero el docente no queda bloqueado: con
  solo poner su clave de OpenRouter en el `.env` copiado de `.env.example`, funciona. El mismo
  modelo (Claude Haiku 5.5) se usa en los dos proveedores, así que la calidad medida se mantiene.
- **Id del modelo:** `MODELO_LLM` usa el id de Anthropic (`claude-haiku-5-5`); para OpenRouter
  se traduce a `anthropic/claude-haiku-5.5` (ids verificados en `GET /api/v1/models` de
  OpenRouter el 2026-11-25). Un id con `/` se pasa tal cual.
- **Pendiente:** smoke test manual por proveedor, documentado en el README (fase 7).

## D2. Datos del GES fuera del repositorio, en `ges/`

- **Decisión:** el zip del GES se descomprime tal cual en `ges/` (ignorada por `.gitignore` y
  `.dockerignore`); la ruta se configura con `RUTA_DATOS` y en Docker se monta como volumen de
  solo lectura. Los casos de evaluación propios sí se versionan, en `ejemplos/`.
- **Por qué:** el enunciado prohíbe datos y credenciales en el repo y en las imágenes; descomprimir
  sin reorganizar evita errores del equipo docente al colocar los archivos.

## D3. Arquitectura: una cadena con una sola llamada al modelo (no agente)

- **Alternativas:** (a) agente con herramientas (buscar producto, calcular precio…);
  (b) cadena: extracción estructurada + motor de reglas en código.
- **Decisión:** (b). El LLM solo extrae menciones (texto, candidatos, cantidad, unidad) con
  salida estructurada; precios, descuentos, crédito y fechas los calcula código con pruebas.
- **Por qué:** la latencia se evalúa (una llamada frente a varias vueltas de agente); los
  cálculos deben ser exactos y reproducibles; y un mensaje no puede influir en un número que el
  modelo nunca produce (defensa ante inyección). Se medirá en la fase 6.

## D4. Límites de la llamada al modelo

- `LLM_TIMEOUT_S=30` y `LLM_MAX_RETRIES=1` por defecto. El comportamiento ante fallo del modelo
  (503 con mensaje claro, nunca un 500 sin manejar ni un pedido inventado) se implementa en la fase 1.
