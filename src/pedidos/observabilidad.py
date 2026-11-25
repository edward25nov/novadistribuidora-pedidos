"""Único módulo que habla con MLflow (trazas de cada solicitud y costo estimado).

Principio: la observabilidad nunca tumba ni frena el servicio.
- Si MLFLOW_TRACKING_URI está vacío, todo es no-op.
- La conexión con el experimento se intenta en segundo plano y se reintenta cada
  `REINTENTO_S`; mientras no esté lista, las solicitudes no se trazan (y /health lo refleja).
- Los spans se exportan de forma asíncrona (MLflow): si el servidor cae a mitad de una carga,
  las solicitudes siguen respondiendo y solo se pierden esas trazas.
- Cualquier excepción de MLflow se registra en el log y se ignora.

Estructura de una traza:
  interpretar_pedido (CHAIN)          entradas: cliente, fecha_hora, mensajes · salidas: respuesta
  ├── extraer (CHAT_MODEL)            modelo, proveedor, tokens, caché, latencia, extracción
  ├── reglas (CHAIN)                  menciones resueltas → pedido calculado
  └── confirmacion (CHAIN)            mensaje al cliente
  Etiquetas de la traza: cliente_id, estado, modelo, proveedor, version_prompt (y `caso` en la
  evaluación) · atributos: total, motivos, costo_usd, tokens.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

import yaml

log = logging.getLogger("pedidos.observabilidad")

REINTENTO_S = 30.0
EXPERIMENTO_POR_DEFECTO = "novadistribuidora-pedidos"
RUTA_PRECIOS = Path(os.getenv(
    "RUTA_PRECIOS", Path(__file__).resolve().parents[2] / "configs" / "precios.yaml"))

# Timeouts cortos para cualquier llamada síncrona del cliente de MLflow.
os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "3")
os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
os.environ.setdefault("MLFLOW_ENABLE_ASYNC_TRACE_LOGGING", "true")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")


# ---------- Costo ----------

def cargar_precios(ruta: Path = RUTA_PRECIOS) -> dict[str, dict[str, float]]:
    try:
        return (yaml.safe_load(ruta.read_text()) or {}).get("modelos", {})
    except FileNotFoundError:
        log.warning("No encuentro %s; el costo no se estimará.", ruta)
        return {}


def costo_usd(uso: dict[str, Any], modelo: str, precios: dict[str, dict[str, float]]
              ) -> float | None:
    """Costo estimado a partir de `usage_metadata` de LangChain.

    `input_tokens` incluye los tokens leídos y escritos en caché; se separan para cobrarlos a
    su precio. Devuelve None si el modelo no está en la tabla de precios.
    """
    modelo = modelo.split("/")[-1].replace(".", "-")     # anthropic/claude-haiku-5.5 → claude-haiku-5-5
    p = precios.get(modelo)
    if not p or not uso:
        return None
    detalle = uso.get("input_token_details") or {}
    leidos = int(detalle.get("cache_read") or 0)
    escritos = int(detalle.get("cache_creation") or 0)
    entrada = max(int(uso.get("input_tokens") or 0) - leidos - escritos, 0)
    salida = int(uso.get("output_tokens") or 0)
    total = (Decimal(entrada) * Decimal(str(p["entrada"]))
             + Decimal(leidos) * Decimal(str(p["cache_lectura"]))
             + Decimal(escritos) * Decimal(str(p["cache_escritura"]))
             + Decimal(salida) * Decimal(str(p["salida"]))) / Decimal(1_000_000)
    return float(total)


# ---------- Trazas ----------

class _SpanNulo:
    def set_inputs(self, *_a, **_k): ...
    def set_outputs(self, *_a, **_k): ...
    def set_attribute(self, *_a, **_k): ...
    def set_attributes(self, *_a, **_k): ...


class Observabilidad:
    def __init__(self, uri: str = "", experimento: str = EXPERIMENTO_POR_DEFECTO,
                 conectar_en_segundo_plano: bool = True):
        self.uri = uri.strip()
        self.experimento = experimento
        self.precios = cargar_precios()
        self._listo = False
        self._ultimo_intento = 0.0
        self._lock = threading.Lock()
        self._ultimo_trace_id: str | None = None
        if self.uri:
            if conectar_en_segundo_plano:
                threading.Thread(target=self._conectar, daemon=True).start()
            else:
                self._conectar()

    @property
    def activa(self) -> bool:
        """True si las trazas se están enviando (o reintenta conectar si ya toca)."""
        if self.uri and not self._listo and time.monotonic() - self._ultimo_intento > REINTENTO_S:
            threading.Thread(target=self._conectar, daemon=True).start()
        return self._listo

    def _conectar(self) -> None:
        with self._lock:
            if self._listo:
                return
            self._ultimo_intento = time.monotonic()
            try:
                import mlflow

                mlflow.set_tracking_uri(self.uri)
                mlflow.set_experiment(self.experimento)
                self._listo = True
                log.info("MLflow listo: %s (experimento %s)", self.uri, self.experimento)
            except Exception as e:      # servidor caído, timeout, etc.
                log.warning("MLflow no disponible (%s); reintento en %.0f s", type(e).__name__,
                            REINTENTO_S)

    @contextmanager
    def span(self, nombre: str, tipo: str = "CHAIN", entradas: Any = None) -> Iterator[Any]:
        """Span de MLflow, o un span nulo si la observabilidad no está activa o falla.

        Las excepciones de la lógica de negocio se propagan; las de MLflow se tragan."""
        if not self.activa:
            yield _SpanNulo()
            return
        try:
            import mlflow

            cm = mlflow.start_span(name=nombre, span_type=tipo)
            span = cm.__enter__()
        except Exception as e:
            log.warning("No pude abrir el span %s: %s", nombre, e)
            yield _SpanNulo()
            return
        try:
            if entradas is not None:
                _seguro(span.set_inputs, entradas)
            yield span
        except BaseException as e:
            _seguro(cm.__exit__, type(e), e, e.__traceback__)
            raise
        else:
            _seguro(cm.__exit__, None, None, None)

    def etiquetar(self, etiquetas: dict[str, Any]) -> None:
        """Etiquetas de la traza activa (para filtrar en la UI de MLflow)."""
        if not self.activa:
            return
        try:
            import mlflow

            mlflow.update_current_trace(tags={k: str(v) for k, v in etiquetas.items()})
            span = mlflow.get_current_active_span()
            if span is not None:
                self._ultimo_trace_id = span.trace_id
        except Exception as e:
            log.warning("No pude etiquetar la traza: %s", e)

    @property
    def ultimo_trace_id(self) -> str | None:
        return self._ultimo_trace_id


def _seguro(funcion, *args) -> None:
    try:
        funcion(*args)
    except Exception as e:
        log.warning("MLflow: %s", e)


NULA = Observabilidad("")
