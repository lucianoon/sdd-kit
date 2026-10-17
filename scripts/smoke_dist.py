"""Instala um wheel fora do checkout e exercita seus comandos e recursos empacotados."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def smoke(wheel: Path) -> None:
    wheel = wheel.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="sdd-dist-") as folder:
        root = Path(folder)
        target = root / "installed"
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-compile", "--target",
                        str(target), str(wheel)], cwd=root, check=True, capture_output=True)
        env = {**os.environ, "PYTHONPATH": str(target), "PYTHONIOENCODING": "utf-8"}
        project = root / "project"
        project.mkdir()
        bootstrap = "from sdd.cli import app; app()"

        def run(*args):
            return subprocess.run([sys.executable, "-c", bootstrap, *args], cwd=project,
                                  env=env, check=True, capture_output=True, encoding="utf-8").stdout

        # Verifica a origem importada para não aprovar acidentalmente um checkout editável.
        imported = subprocess.run([sys.executable, "-c", "import sdd; print(sdd.__file__)"],
                                  cwd=project, env=env, check=True, capture_output=True, encoding="utf-8")
        assert Path(imported.stdout.strip()).is_relative_to(target), imported.stdout
        version = run("--version").strip()
        assert version.startswith("sdd-kit "), version
        run("init", "--preset", "padrao")
        run("validate")
        report = json.loads(run("analyze", "--json"))
        assert report["ok"] and report["summary"]["features"] == 1, report
        packet = json.loads(run("guide", "exemplo", "--stage", "plan", "--json"))
        assert packet["feature"] == "exemplo" and packet["stage"] == "plan", packet
        run("integrate", "all")
        assert (project / ".agents/skills/sdd-plan/SKILL.md").is_file()
        run("adequacy", "template", "exemplo")
        assert (project / "specs/reviews/exemplo.yaml").is_file()
        source = project / "foreign.md"
        source.write_text("### Requirement: Example\n#### Scenario: Valid\n- **WHEN** invoked\n- **THEN** returns a value\n", encoding="utf-8")
        imported = json.loads(run("import-spec", "foreign.md", "--format", "openspec", "--feature", "foreign"))
        assert imported["status"] == "draft" and (project / imported["draft"]).is_file()
        catalog = run("profile", "--catalog")
        assert "N-01" in catalog and "P-01" in catalog, catalog
        print(f"{version}: wheel instalado, CLI, catálogo, analyze e guide aprovados")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    smoke(parser.parse_args().wheel)
