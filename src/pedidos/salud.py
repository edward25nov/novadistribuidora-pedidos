"""Estado de las dependencias para GET /health. Nunca bloquea más de ~1 s."""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

TIMEOUT_PING_S = 1.0
CACHE_S = 2.0


class VerificadorMlflow:
    """Hace GET {uri}/health con timeout corto y guarda el resultado unos segundos,
    para que /health no se vuelva lento si MLflow está caído."""

    def __init__(self, uri: str, reloj: Callable[[], float] = time.monotonic):
        self.uri = uri.rstrip("/")
        self._reloj = reloj
        self._ultimo: tuple[float, str] | None = None

    def estado(self) -> str:
        """'ok', 'no_configurado' o un motivo de falla."""
        if not self.uri:
            return "no_configurado"
        ahora = self._reloj()
        if self._ultimo and ahora - self._ultimo[0] < CACHE_S:
            return self._ultimo[1]
        try:
            r = httpx.get(f"{self.uri}/health", timeout=TIMEOUT_PING_S)
            resultado = "ok" if r.status_code == 200 else f"responde {r.status_code}"
        except httpx.HTTPError as e:
            resultado = f"no disponible ({type(e).__name__})"
        self._ultimo = (ahora, resultado)
        return resultado
