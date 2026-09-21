"""Fixtures compartidos de apps/api/tests.

`_isolated_work_dir` es autouse: cada test escribe sus subidas bajo el `tmp_path` de
pytest (via `CEM_WORK_DIR`) en vez del temp real del sistema, para no acumular
carpetas huerfanas al correr la suite muchas veces (CLAUDE.md 6, "nada real se
commitea"; aqui aplica el mismo criterio de higiene a los artefactos de test).
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_work_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CEM_WORK_DIR", str(tmp_path / "work"))


@pytest.fixture
def synthetic_export_dir() -> Path:
    """El fixture sintetico mas completo de core: las 5 categorias juntas."""
    root = Path(__file__).resolve().parents[3]
    return root / "packages/core/tests/fixtures/synthetic/batched-full"
