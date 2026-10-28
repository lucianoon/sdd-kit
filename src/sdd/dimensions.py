"""Dimensões de requisito implícito: perguntas do catálogo e aviso por termos.

Determinístico e sem LLM. Os termos são radicais comparados sem acento e sem caixa, no
início de uma palavra. A detecção é heurística: o aviso pede que a dimensão seja levantada
e declarada em `dimensions`; nunca bloqueia nem substitui a conversa com o usuário.
"""
from __future__ import annotations

import re

from .analysis import _fold
from .models import Spec

CATALOG: dict[str, dict[str, list[str]]] = {
    "persistencia": {
        "terms": ["persist", "salvar", "armazen", "banco de dados", "database"],
        "questions": [
            "Persistência: o que fica gravado se a operação falhar no meio, e como o estado parcial é desfeito?",
            "Persistência: por quanto tempo os dados ficam guardados e quem pode apagá-los?",
        ],
    },
    "autenticacao": {
        "terms": ["autentic", "login", "logad", "senha", "credenc", "permiss", "autoriz", "password",
                  "permission", "authoriz", "authentic"],
        "questions": [
            "Autenticação: quem pode executar esta ação, e o que recebe quem não pode?",
            "Autenticação: o que acontece quando a sessão ou a credencial expira no meio da operação?",
        ],
    },
    "pagamentos": {
        "terms": ["pagament", "pagar", "reembols", "estorn", "fatura", "boleto", "payment", "refund",
                  "invoice"],
        "questions": [
            "Pagamentos: o que acontece se a cobrança for feita e a resposta não chegar (resultado desconhecido)?",
            "Pagamentos: como funcionam reembolso, estorno e cobrança parcial?",
        ],
    },
    "chamadas-externas": {
        "terms": ["api externa", "servico externo", "webhook", "api de terceiros", "servico de terceiros",
                  "third-party", "external api", "external service"],
        "questions": [
            "Chamadas externas: o que acontece quando o serviço externo demora ou está fora do ar?",
            "Chamadas externas: repetir a chamada é seguro, ou ela pode duplicar um efeito?",
        ],
    },
    "concorrencia": {
        "terms": ["concorren", "simultane", "ao mesmo tempo", "em paralelo", "condicao de corrida",
                  "concurren", "simultaneous", "race condition", "in parallel"],
        "questions": [
            "Concorrência: o que acontece com duas operações simultâneas sobre o mesmo registro?",
            "Concorrência: qual das operações vence, e o que a outra recebe?",
        ],
    },
    "transicoes-de-estado": {
        "terms": ["transicao", "transicoes", "maquina de estados", "cancelar", "cancelad", "cancelament",
                  "state machine", "transition"],
        "questions": [
            "Transições de estado: quais transições são permitidas e quais são proibidas?",
            "Transições de estado: o que acontece ao repetir uma transição já feita (ex.: cancelar duas vezes)?",
        ],
    },
}
_TERMS = {name: re.compile(r"(?<![\w-])(" + "|".join(re.escape(t) for t in d["terms"]) + r")")
          for name, d in CATALOG.items()}


def questions(names: list[str]) -> list[str]:
    unknown = [n for n in names if n not in CATALOG]
    if unknown:
        raise ValueError(f"dimensão desconhecida: {', '.join(unknown)} (disponíveis: {', '.join(CATALOG)})")
    return [q for n in names for q in CATALOG[n]["questions"]]


def detect(spec: Spec) -> dict[str, list[str]]:
    """Dimensões citadas no texto e ainda não declaradas, com os termos encontrados."""
    parts = [spec.summary]
    for req in spec.requirements:
        parts.append(req.description)
        for ac in req.acceptance:
            parts += [ac.given, ac.when, ac.then, *ac.forbidden]
    text = _fold("\n".join(parts))
    found = {}
    for name, pattern in _TERMS.items():
        terms = sorted(set(pattern.findall(text)))
        if terms and name not in spec.dimensions:
            found[name] = terms
    return found


def check(rel: str, spec: Spec) -> list[str]:
    return [f"{rel}: cita {name} ({', '.join(terms)}) sem declarar em `dimensions`; pergunte ao usuário "
            f"e registre em open_questions ou assumptions: {' '.join(CATALOG[name]['questions'])}"
            for name, terms in detect(spec).items()]
