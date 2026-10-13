"""Leitura de código-fonte compartilhada por arch e mutation."""
from __future__ import annotations

import io
import tokenize


def python_string_lines(text: str) -> set[int]:
    """Linhas (1-based) ocupadas por strings de várias linhas (docstrings, textos longos).

    Usa o tokenizador do Python: contar aspas triplas na linha erra quando elas aparecem
    dentro de uma string comum (ex.: '\"\"\"') e inverte o estado pelo resto do arquivo.
    Se o arquivo não tokeniza (erro de sintaxe), devolve vazio.
    """
    lines: set[int] = set()
    start = 0
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.STRING and tok.end[0] > tok.start[0]:
                lines.update(range(tok.start[0], tok.end[0] + 1))
            elif getattr(tokenize, "FSTRING_START", None) == tok.type:
                start = tok.start[0]
            elif getattr(tokenize, "FSTRING_END", None) == tok.type and tok.end[0] > start:
                lines.update(range(start, tok.end[0] + 1))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return set()
    return lines
