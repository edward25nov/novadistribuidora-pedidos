"""Integración con los datos reales del GES (se omite si no están, p. ej. en CI)."""

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
GES = RAIZ / "ges"

pytestmark = pytest.mark.skipif(
    not (GES / "ejemplos/mensajes_dev.jsonl").is_file(), reason="datos del GES no disponibles"
)


def test_motor_reproduce_los_84_casos_dev():
    sys.path.insert(0, str(RAIZ / "scripts"))
    from verificar_reglas_dev import main

    assert main(GES) == 0
