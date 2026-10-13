"""Execução de comandos externos com timeout que mata a árvore inteira.

`subprocess.run(cmd, shell=True, timeout=...)` mata só o shell intermediário: o processo
de verdade (o neto) fica órfão e continua rodando. Num mutante que gera loop infinito,
isso vaza um processo a 100% de CPU por execução. Aqui o comando roda num grupo próprio
e o timeout mata o grupo (POSIX) ou a árvore (Windows).
"""
from __future__ import annotations

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
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    else:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def run_shell(cmd: str, cwd, timeout: int, env: dict | None = None) -> Result:
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32" \
        else {"start_new_session": True}
    p = subprocess.Popen(cmd, shell=True, cwd=cwd, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, **kwargs)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(p)
        out, err = p.communicate()
        text = (out + err).decode("utf-8", errors="replace")
        return Result(-1, text, True)
    return Result(p.returncode, (out + err).decode("utf-8", errors="replace"), False)
