"""Execução de comandos externos com timeout que mata a árvore inteira.

`subprocess.run(cmd, shell=True, timeout=...)` mata só o shell intermediário: o processo
de verdade (o neto) fica órfão e continua rodando. Num mutante que gera loop infinito,
isso vaza um processo a 100% de CPU por execução. Aqui o comando roda num grupo próprio
e o timeout mata o grupo (POSIX) ou a árvore (Windows).
"""
from __future__ import annotations

import locale
import os
import signal
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class Result:
    returncode: int  # -1 quando estourou o timeout
    output: str  # stdout + stderr decodificados
    timed_out: bool


def _kill_tree(p: subprocess.Popen) -> None:
    if sys.platform == "win32":
        # sdd: no-mutate (ramo Windows: coberto pelo job windows do CI, não pela mutação no Linux)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)  # sdd: no-mutate
    else:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def _decode(data: bytes) -> str:
    """UTF-8 primeiro; se não for válido, a codificação do sistema (ex.: cp1252 no Windows)."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        system = (locale.getencoding() if hasattr(locale, "getencoding")  # Python 3.11+
                  else locale.getpreferredencoding(False))  # sdd: no-mutate (só Python 3.10)
        return data.decode(system or "utf-8", errors="replace")


def run_shell(cmd: str, cwd, timeout: int, env: dict | None = None) -> Result:
    env = dict(os.environ if env is None else env)
    env.setdefault("PYTHONIOENCODING", "utf-8")  # filhos Python escrevem UTF-8 no pipe
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32" \
        else {"start_new_session": True}
    p = subprocess.Popen(cmd, shell=True, cwd=cwd, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, **kwargs)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(p)
        out, err = p.communicate()
        return Result(-1, _decode(out + err), True)
    return Result(p.returncode, _decode(out + err), False)
