"""Demonstrate an actual discount regression and repair in a disposable project."""
from pathlib import Path
import shutil
import os
import subprocess
import sys
import tempfile


def main():
    example = Path(__file__).resolve().parents[1] / "examples/pytest"
    with tempfile.TemporaryDirectory(prefix="sdd-demo-") as folder:
        root = Path(folder) / "project"
        shutil.copytree(example, root)
        source = root / "src/pedido.py"
        original = source.read_text(encoding="utf-8")
        env = {**os.environ, "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""),
               "PYTHONIOENCODING": "utf-8"}
        def check(expected):
            result = subprocess.run([sys.executable, "-c", "from sdd.cli import app; app()", "check"],
                                    cwd=root, env=env, capture_output=True, encoding="utf-8", timeout=120)
            print(result.stdout)
            if result.returncode != expected:
                raise RuntimeError(f"check: esperado {expected}, obtido {result.returncode}: {result.stderr}")
        print("1. Exemplo original: deve passar")
        check(0)
        print("2. Desconto incorreto: AC-003 deve reprovar")
        source.write_text(original.replace("valor * 0.9", "valor * 0.8"), encoding="utf-8")
        # Avoid timestamp/size-based bytecode reuse after replacing equal-length text.
        shutil.rmtree(source.parent / "__pycache__", ignore_errors=True)
        check(1)
        print("3. Correção: deve passar")
        source.write_text(original, encoding="utf-8")
        shutil.rmtree(source.parent / "__pycache__", ignore_errors=True)
        check(0)
        print("Demonstração aprovada: regressão detectada e correção verificada.")


if __name__ == "__main__":
    main()
