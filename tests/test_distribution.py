"""Verifica o artefato instalável real, sem importar sdd do checkout no subprocesso."""
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest


@pytest.fixture(scope="module")
def wheel(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path_factory.mktemp("wheel")
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(output)],
                   cwd=root, check=True, capture_output=True, env={**os.environ, "PYTHONUTF8": "1"})
    return next(output.glob("*.whl"))


def run_smoke(wheel, cwd):
    root = Path(__file__).resolve().parents[1]
    # O smoke imprime acentos; sem isto o Windows escreve cp1252 no pipe e a leitura utf-8 quebra.
    return subprocess.run([sys.executable, str(root / "scripts/smoke_dist.py"), str(wheel)],
                          cwd=cwd, capture_output=True, encoding="utf-8",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def test_ac_113_wheel_instalado_funciona_fora_do_checkout(tmp_path, wheel):
    result = run_smoke(wheel, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "CLI, catálogo, analyze e guide aprovados" in result.stdout


def test_ac_113_wheel_ausente_e_diagnosticado_antes_da_instalacao(tmp_path):
    result = run_smoke(tmp_path / "ausente.whl", tmp_path)
    assert result.returncode != 0 and "FileNotFoundError" in result.stderr


@pytest.mark.parametrize("missing", ["N-01", "P-01"])
def test_ac_113_catalogo_incompleto_bloqueia_distribuicao(tmp_path, wheel, missing):
    # Corrompe somente o catálogo no pacote real: um grupo presente não mascara o outro ausente.
    damaged = tmp_path / wheel.name
    with zipfile.ZipFile(wheel) as source, zipfile.ZipFile(damaged, "w") as target:
        for entry in source.infolist():
            data = source.read(entry.filename)
            if entry.filename == "sdd/profiles/agentes.yaml":
                data = data.replace(f"id: {missing}".encode(), f"id: {missing[0]}-99".encode())
            target.writestr(entry, data)
    result = run_smoke(damaged, tmp_path)
    assert result.returncode != 0 and "AssertionError" in result.stderr
