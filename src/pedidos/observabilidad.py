"""Único módulo que habla con MLflow (trazas de cada solicitud y costo estimado).

Principio: la observabilidad nunca tumba ni frena el servicio.
- Si MLFLOW_TRACKING_URI está vacío, todo es no-op.
- La conexión con el experimento se intenta en segundo plano con espera creciente (1, 2, 4… s,
  hasta `REINTENTO_S`) o en cuanto /health ve MLflow arriba; mientras no esté lista, las
  solicitudes no se trazan y /health dice "mlflow: conectando".
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

import contextvars
import logging
import os
import threading
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
        self._despertar = threading.Event()
        self._ultimo_trace_id: str | None = None
        if self.uri:
            if conectar_en_segundo_plano:
                threading.Thread(target=self._bucle_conexion, daemon=True,
                                 name="mlflow-conexion").start()
            else:
                self._intentar_conectar()

    @property
    def activa(self) -> bool:
        """True si el experimento está listo y las trazas se envían."""
        return self._listo

    def despertar(self) -> None:
        """Pide reintentar ya (p. ej. cuando /health ve que MLflow volvió)."""
        self._despertar.set()

    def _intentar_conectar(self) -> bool:
        try:
            import mlflow

            mlflow.set_tracking_uri(self.uri)
            mlflow.set_experiment(self.experimento)
        except Exception as e:      # servidor caído, timeout, etc.
            log.warning("MLflow no disponible todavía (%s)", type(e).__name__)
            return False
        self._listo = True
        log.info("MLflow listo: %s (experimento %s)", self.uri, self.experimento)
        return True

    def _bucle_conexion(self) -> None:
        """Un solo hilo: reintenta con espera creciente 1, 2, 4… hasta REINTENTO_S, o antes si
        alguien llama a despertar(). Al arrancar con compose, MLflow suele tardar unos
        segundos más que la API: así las primeras solicitudes ya se trazan."""
        espera = 1.0
        while not self._intentar_conectar():
            self._despertar.wait(timeout=espera)
            self._despertar.clear()
            espera = min(espera * 2, REINTENTO_S)

    @contextmanager
    def span(self, nombre: str, tipo: str = "CHAIN", entradas: Any = None,
             raiz: bool = False) -> Iterator[Any]:
        """Span de MLflow, o un span nulo si no se está trazando o MLflow falla.

        La decisión de trazar se toma UNA vez por solicitud, en el span raíz (`raiz=True`): los
        hijos solo se abren si hay un span activo de MLflow. Así una reconexión a mitad de una
        solicitud no genera trazas huérfanas. Las excepciones de la lógica de negocio se
        propagan; las de MLflow se tragan."""
        if raiz:
            trazar = self._listo
        else:
            trazar = _trazando.get() and _hay_span_activo()
        if not trazar:
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
        token = _trazando.set(True) if raiz else None
        try:
            if entradas is not None:
                _seguro(span.set_inputs, entradas)
            yield span
        except BaseException as e:
            _seguro(cm.__exit__, type(e), e, e.__traceback__)
            raise
        else:
            _seguro(cm.__exit__, None, None, None)
        finally:
            if token is not None:
                _trazando.reset(token)

    def etiquetar(self, etiquetas: dict[str, Any]) -> None:
        """Etiquetas de la traza en curso (para filtrar en la UI de MLflow)."""
        if not (_trazando.get() and _hay_span_activo()):
            return
        try:
            import mlflow

            mlflow.update_current_trace(tags={k: str(v) for k, v in etiquetas.items()})
            self._ultimo_trace_id = mlflow.get_current_active_span().trace_id
        except Exception as e:
            log.warning("No pude etiquetar la traza: %s", e)

    @property
    def ultimo_trace_id(self) -> str | None:
        return self._ultimo_trace_id


_trazando: contextvars.ContextVar[bool] = contextvars.ContextVar("trazando", default=False)


def _hay_span_activo() -> bool:
    try:
        import mlflow

        return mlflow.get_current_active_span() is not None
    except Exception:
        return False


def _seguro(funcion, *args) -> None:
    try:
        funcion(*args)
    except Exception as e:
        log.warning("MLflow: %s", e)


NULA = Observabilidad("")
