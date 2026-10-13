import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sdd.cli import app
from sdd.diff import matches

runner = CliRunner()

CONFIG = """\
version: 1
tests: {command: "true", junit: .sdd/junit.xml}
code: ["src/**"]
"""
SPEC = """\
feature: pedidos
version: 1
requirements:
  - id: REQ-001
    description: d
    acceptance:
      - {id: AC-001, given: g, when: w, then: t}
paths: ["src/pedidos/**"]
"""


def git(root: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=root, env=env, check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout


def write(root: Path, rel: str, text: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(encoding="utf-8", data=text)


@pytest.fixture
def repo(tmp_path):
    """Repo com branch base `main` e uma branch de trabalho."""
    git(tmp_path, "init", "-q", "-b", "main")
    write(tmp_path, "specs/sdd.yaml", CONFIG)
    write(tmp_path, "specs/features/FEATURE-001/spec.yaml", SPEC)
    write(tmp_path, "src/pedidos/api.py", "x = 1\n")
    write(tmp_path, "README.md", "r\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "checkout", "-qb", "trabalho")
    return tmp_path


def commit(root: Path, msg: str = "mudança"):
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg)


def run_diff(root: Path):
    return runner.invoke(app, ["diff", "--base", "main", "-C", str(root)])


def test_ac_010_codigo_sem_spec_reprova(repo):
    write(repo, "src/pedidos/api.py", "x = 2\n")
    commit(repo)
    r = run_diff(repo)
    assert r.exit_code == 1
    assert "pedidos: código alterado sem mudança" in r.stderr


def test_ac_011_codigo_e_spec_juntos_aprova(repo):
    write(repo, "src/pedidos/api.py", "x = 2\n")
    write(repo, "specs/features/FEATURE-001/spec.yaml", SPEC.replace("version: 1", "version: 2"))
    commit(repo)
    assert run_diff(repo).exit_code == 0


def test_ac_012_codigo_sem_dono_reprova(repo):
    write(repo, "src/pagamentos/core.py", "y = 1\n")
    commit(repo)
    r = run_diff(repo)
    assert r.exit_code == 1
    assert "src/pagamentos/core.py: código sem feature dona" in r.output


def test_ac_013_trailer_libera_com_motivo(repo):
    write(repo, "src/pedidos/api.py", "x = 2\n")
    commit(repo, "refactor: renomeia variável\n\nSDD-No-Spec-Change: só renomeação interna")
    r = run_diff(repo)
    assert r.exit_code == 0, r.output
    assert "liberado por SDD-No-Spec-Change: pedidos" in r.output


def test_ac_014_so_spec_aprova_com_aviso(repo):
    write(repo, "specs/features/FEATURE-001/spec.yaml", SPEC.replace("version: 1", "version: 2"))
    commit(repo)
    r = run_diff(repo)
    assert r.exit_code == 0
    assert "AVISO pedidos: spec alterada sem código" in r.output


def test_ac_015_nao_commitado_e_nao_rastreado_contam(repo):
    write(repo, "src/pedidos/api.py", "x = 3\n")          # modificado, não commitado
    assert run_diff(repo).exit_code == 1
    git(repo, "checkout", "--", "src/pedidos/api.py")
    write(repo, "src/pedidos/novo.py", "z = 1\n")         # não rastreado
    assert run_diff(repo).exit_code == 1


def test_arquivo_fora_de_code_e_ignorado(repo):
    write(repo, "README.md", "outro\n")
    commit(repo)
    assert run_diff(repo).exit_code == 0


def test_ac_054_falha_do_git_sai_com_2(repo):
    r = runner.invoke(app, ["diff", "--base", "nao-existe", "-C", str(repo)])
    assert r.exit_code == 2


@pytest.mark.parametrize("path,pattern,ok", [
    ("src/a/b/c.py", "src/**", True),
    ("src/c.py", "src/*.py", True),
    ("src/a/c.py", "src/*.py", False),
    ("src/a/b/c.py", "src/**/c.py", True),
    ("src/c.py", "src/**/c.py", True),
    ("srcx/c.py", "src/**", False),
    ("src/a1.py", "src/a?.py", True),
    ("src/a12.py", "src/a?.py", False),
    ("src/a/.py", "src/a?.py", False),
])
def test_glob(path, pattern, ok):
    assert matches(path, [pattern]) is ok


def test_ac_014_sem_aviso_quando_codigo_muda_junto(repo):
    write(repo, "src/pedidos/api.py", "x = 2\n")
    write(repo, "specs/features/FEATURE-001/spec.yaml", SPEC.replace("version: 1", "version: 2"))
    commit(repo)
    r = run_diff(repo)
    assert r.exit_code == 0 and "AVISO" not in r.output


def test_ac_014_spec_sem_paths_nao_gera_aviso(repo):
    write(repo, "specs/features/FEATURE-001/spec.yaml",
          SPEC.replace('paths: ["src/pedidos/**"]\n', "").replace("version: 1", "version: 2"))
    commit(repo)
    r = run_diff(repo)
    assert "spec alterada sem código" not in r.output
