"""Timeout mata a árvore inteira de processos (sem órfãos queimando CPU)."""
import os
import subprocess
import sys
import time

from sdd.procs import run_shell

PY = sys.executable


def alive(pid: int) -> bool:
    if sys.platform == "win32":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # zumbi ainda aparece; confere o estado em /proc quando existir
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            return f.read().split()[2] != "Z"
    except FileNotFoundError:
        return True


def test_ac_059_timeout_mata_o_processo_neto(tmp_path):
    pid_file = tmp_path / "pid"
    # "&& echo fim" impede o shell de se substituir pelo python: o python vira neto.
    cmd = (f"{PY} -c \"import os, time, pathlib; "
           f"pathlib.Path(r'{pid_file}').write_text(str(os.getpid())); time.sleep(60)\" && echo fim")
    start = time.monotonic()
    r = run_shell(cmd, tmp_path, timeout=2)
    assert r.timed_out and r.returncode == -1
    assert time.monotonic() - start < 20
    pid = int(pid_file.read_text(encoding="utf-8"))
    for _ in range(20):
        if not alive(pid):
            break
        time.sleep(0.1)
    assert not alive(pid), f"processo {pid} ficou órfão"


def test_run_shell_saida_e_codigo(tmp_path):
    r = run_shell(f"{PY} -c \"print('olá'); raise SystemExit(3)\"", tmp_path, timeout=30)
    assert r.returncode == 3 and not r.timed_out and "olá" in r.output
