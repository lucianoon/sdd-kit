import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sdd.cli import app
from sdd.diff import changes, matches

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
    commit(repo, "refactor: renomeia variável\n\nSDD-No-Spec-Change(pedidos): só renomeação interna")
    r = run_diff(repo)
    assert r.exit_code == 0, r.output
    assert "liberado por SDD-No-Spec-Change: pedidos" in r.output
    assert "só renomeação interna" in r.output


def test_ac_090_excecao_nao_libera_outra_feature(repo):
    spec = SPEC.replace("pedidos", "pagamentos").replace("REQ-001", "REQ-002").replace("AC-001", "AC-002")
    write(repo, "specs/features/FEATURE-002/spec.yaml", spec)
    write(repo, "src/pagamentos/api.py", "x = 1\n")
    commit(repo, "segunda feature")
    git(repo, "branch", "-f", "main", "HEAD")
    write(repo, "src/pedidos/api.py", "x = 2\n")
    write(repo, "src/pagamentos/api.py", "x = 2\n")
    commit(repo, "refactor\n\nSDD-No-Spec-Change(pedidos): renomeação interna")
    r = run_diff(repo)
    assert r.exit_code == 1
    assert "liberado por SDD-No-Spec-Change: pedidos" in r.stdout
    assert "pagamentos: código alterado sem mudança" in r.stderr


@pytest.mark.parametrize("trailer", [
    "SDD-No-Spec-Change: renomeação interna",
    "SDD-No-Spec-Change(pedidos):   ",
    "SDD-No-Spec-Change(inexistente): renomeação interna",
    "SDD-No-Spec-Change(): renomeação interna",
])
def test_ac_090_excecao_invalida_reprova(repo, trailer):
    write(repo, "src/pedidos/api.py", "x = 2\n")
    commit(repo, "refactor\n\n" + trailer)
    assert run_diff(repo).exit_code == 1


def test_ac_090_global_legado_exige_opt_in_e_avisa(repo):
    write(repo, "specs/sdd.yaml", CONFIG + "allow_global_diff_override: true\n")
    write(repo, "src/pedidos/api.py", "x = 2\n")
    commit(repo, "refactor\n\nSDD-No-Spec-Change: renomeação interna")
    r = run_diff(repo)
    assert r.exit_code == 0, r.output
    assert "global está deprecado" in r.output


def test_ac_090_excecao_nao_libera_codigo_sem_dono(repo):
    write(repo, "src/sem-dono.py", "x = 2\n")
    commit(repo, "refactor\n\nSDD-No-Spec-Change(pedidos): renomeação interna")
    r = run_diff(repo)
    assert r.exit_code == 1 and "código sem feature dona" in r.stderr


def test_ac_090_dataset_exige_spec_mesmo_com_excecao(repo):
    from sdd import core
    from sdd.diff import evaluate
    from sdd.models import Eval

    proj = core.load(repo)
    spec = next(iter(proj.specs.values()))
    spec.evals = [Eval(id="EVAL-001", metric="accuracy", dataset="evals/casos.jsonl",
                       min_cases=1, threshold={"min": 0.9})]
    res = evaluate(proj, ["evals/casos.jsonl"], "SDD-No-Spec-Change(pedidos): casos novos")
    assert not res.ok and any("dataset de eval alterado" in v for v in res.violations)


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


@pytest.mark.parametrize("name", ["validação.py", "com espaço.py", 'com"aspas.py', "com\ttab.py", "com\nlinha.py", "com\rretorno.py"])
@pytest.mark.parametrize("state", ["modified", "staged", "untracked"])
def test_ac_101_nomes_especiais_preservados_e_cobrados(repo, name, state):
    if os.name == "nt" and any(c in name for c in '\"\t\n\r'):
        pytest.skip("nome não permitido no Windows")
    git(repo, "config", "core.quotePath", "true")
    path = f"src/pedidos/{name}"
    if state != "untracked":
        write(repo, path, "x = 1\n")
        commit(repo, "arquivo de base")
    write(repo, path, "x = 2\n")
    if state == "staged":
        git(repo, "add", "--", path)
    changed, _, _ = changes(repo, "HEAD")
    assert changed == [path]
    result = runner.invoke(app, ["diff", "--base", "HEAD", "-C", str(repo)])
    assert result.exit_code == 1, result.output
    assert "pedidos: código alterado sem mudança" in result.stderr


def test_ac_101_arquivo_unicode_sem_dono_reprova(repo):
    git(repo, "config", "core.quotePath", "true")
    write(repo, "src/órfão com espaço.py", "x = 2\n")
    commit(repo)
    result = run_diff(repo)
    assert result.exit_code == 1
    assert "src/órfão com espaço.py: código sem feature dona" in result.stderr


def test_arquivo_fora_de_code_e_ignorado(repo):
    write(repo, "README.md", "outro\n")
    commit(repo)
    assert run_diff(repo).exit_code == 0


def test_ac_054_falha_do_git_sai_com_2(repo):
    r = runner.invoke(app, ["diff", "--base", "nao-existe", "-C", str(repo)])
    assert r.exit_code == 2


def test_ac_087_edicao_cosmetica_da_spec_nao_libera_codigo(repo):
    # só acrescenta comentário e muda espaçamento: o conteúdo é o mesmo
    write(repo, "src/pedidos/api.py", "x = 2\n")
    write(repo, "specs/features/FEATURE-001/spec.yaml", "# revisado pelo analista\n" + SPEC + "\n")
    commit(repo)
    r = run_diff(repo)
    assert r.exit_code == 1, r.output
    assert "pedidos: código alterado sem mudança" in r.stderr


def test_ac_087_semantica_documentada(repo):
    from sdd.diff import semantic_hash

    base = "feature: p\nversion: 1\nrequirements: []\n"
    cosmetic = ("# cabeçalho comentado\n"
                "version: 1\nfeature: p\n  \n"
                "requirements: []\n")  # chaves reordenadas, comentário e espaços extras
    assert semantic_hash(base) == semantic_hash(cosmetic)
    assert semantic_hash(base) != semantic_hash(base.replace("version: 1", "version: 2"))
    assert semantic_hash("") == semantic_hash("  \n")  # vazio e só espaço são o mesmo vazio


def test_ac_088_mudanca_comentarios_alienigenas(repo):
    # YAML quebrado: compara como texto cru e aceita mudança real
    from sdd.diff import semantic_hash

    broken = "feature: [\n  a, b\n"
    assert semantic_hash(broken) != semantic_hash(broken + "  c\n")
    assert semantic_hash(broken + "\n") == semantic_hash(broken)


def test_ac_088_filho_do_git_indisponivel_conserva_mudanca(tmp_path, monkeypatch):
    from sdd.diff import GitError, _meaningful_spec_change
    import sdd.diff as d

    monkeypatch.setattr(d, "_git_show", lambda root, ref, path: (_ for _ in ()).throw(GitError("boom")))
    assert _meaningful_spec_change(tmp_path, "specs/features/FEATURE-001/spec.yaml", "mb") is True


def test_ac_087_spec_removida_do_disco_e_mudanca_real(repo):
    # unidade: spec sem arquivo no disco é tratada como mudança real, não cosmética
    from sdd.diff import _meaningful_spec_change

    assert _meaningful_spec_change(repo, "specs/features/INEXISTENTE/spec.yaml", "mb") is True
    # a spec não existe mais no disco: não é reformatar, é abrir mão do contrato
    write(repo, "specs/features/FEATURE-002/spec.yaml",
          SPEC.replace("pedidos", "pagamentos"))
    write(repo, "src/pedidos/api.py", "x = 2\n")
    (repo / "specs/features/FEATURE-001/spec.yaml").unlink()
    commit(repo)
    r = run_diff(repo)
    assert r.exit_code == 1, r.output
    assert "src/pedidos/api.py: código sem feature dona" in r.output


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
    ("src/com\nlinha.py", "src/**", True),
    ("src/api.py\n", "src/api.py", False),
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
