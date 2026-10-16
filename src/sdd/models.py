"""Schema canônico das especificações. Fonte única: daqui sai o JSON Schema."""
from __future__ import annotations

from typing import Annotated, Literal
from pathlib import PurePosixPath, PureWindowsPath

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


def relative_path(value: str) -> str:
    p = PurePosixPath(value)
    if (not value or value.strip() != value or value in (".", "./") or p.is_absolute()
            or PureWindowsPath(value).drive or "\\" in value or ".." in p.parts or "\0" in value):
        raise ValueError("caminho deve ser relativo ao projeto, sem raiz, traversal ou barras invertidas")
    return value

ProjectPath = Annotated[str, AfterValidator(relative_path)]

REQ_PATTERN = r"^REQ-\d{3,}$"
AC_PATTERN = r"^AC-\d{3,}$"
NFR_PATTERN = r"^NFR-\d{3,}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Acceptance(Strict):
    id: str = Field(pattern=AC_PATTERN)
    given: str
    when: str
    then: str
    # O que NÃO pode acontecer neste cenário (efeitos proibidos). O teste do AC deve verificá-los.
    forbidden: list[str] = []


class Requirement(Strict):
    id: str = Field(pattern=REQ_PATTERN)
    description: str
    acceptance: list[Acceptance] = Field(min_length=1)


# --- Desenho arquitetural ---------------------------------------------------

class Number(Strict):
    """Número que orienta o desenho. Com `id`, vira requisito não funcional verificável:
    exige um teste/benchmark com o ID no nome, igual a um critério de aceitação."""
    id: str | None = Field(None, pattern=NFR_PATTERN)
    metric: str = Field(min_length=1)
    max: float | None = None
    min: float | None = None
    unit: str = Field(min_length=1)
    at: str = ""  # condição em que vale (ex.: "50 req/s de pico")
    source: str = Field(min_length=1)  # de onde veio: medição, contrato, estimativa do PO...

    @model_validator(mode="after")
    def _limite(self):
        if self.max is None and self.min is None:
            raise ValueError("informe max e/ou min")
        if self.max is not None and self.min is not None and self.min > self.max:
            raise ValueError("min maior que max")
        return self

    def describe(self) -> str:
        parts = []
        if self.min is not None:
            parts.append(f">= {self.min:g}")
        if self.max is not None:
            parts.append(f"<= {self.max:g}")
        return f"{self.metric} {' e '.join(parts)} {self.unit}" + (f" @ {self.at}" if self.at else "")


class Ingress(Strict):
    via: str = Field(min_length=1)  # http, stream, arquivo, fila...
    source: str = ""
    frequency: str = Field(min_length=1)


class Egress(Strict):
    to: str = Field(min_length=1)  # banco analítico, cache em memória, API...
    consumers: list[str] = []
    freshness: str = ""  # atraso aceitável para quem consome


class DataFlow(Strict):
    ingress: list[Ingress] = Field(min_length=1)
    egress: list[Egress] = Field(min_length=1)


class Alternative(Strict):
    name: str = Field(min_length=1)
    chosen: bool = False
    why: str = ""
    why_not: str = ""

    @model_validator(mode="after")
    def _justificativa(self):
        if self.chosen and not self.why.strip():
            raise ValueError("alternativa escolhida precisa de `why`")
        if not self.chosen and not self.why_not.strip():
            raise ValueError("alternativa descartada precisa de `why_not`")
        return self


class Risk(Strict):
    area: Literal["performance", "security", "availability", "data_integrity",
                  "cost", "compliance", "other"]
    severity: Literal["low", "medium", "high"]
    description: str = Field(min_length=1)
    mitigated_by: list[str] = []  # IDs de AC ou NFR desta spec
    accepted: str = ""  # risco aceito conscientemente: por quê

    @model_validator(mode="after")
    def _tratamento(self):
        if not self.mitigated_by and not self.accepted.strip():
            raise ValueError("risco precisa de `mitigated_by` (AC/NFR) ou `accepted` (motivo)")
        return self


class Retry(Strict):
    max_attempts: int = Field(ge=1)  # 1 = sem retry
    backoff: Literal["none", "fixed", "exponential"] = "exponential"


class Dependency(Strict):
    """Dependência externa e como o sistema se comporta quando ela falha."""
    name: str = Field(min_length=1)
    kind: Literal["llm", "vector_store", "database", "cache", "queue",
                  "external_api", "tool", "process"]
    timeout_ms: int = Field(ge=1)  # sem timeout não existe: uma chamada pendurada derruba o fluxo
    retry: Retry
    fallback: str = Field(min_length=1)  # o que acontece quando esgota; "nenhum: <motivo>" é válido
    side_effects: bool  # escreve, cobra, envia, cria pedido...
    idempotent: bool  # repetir a operação produz o mesmo resultado?
    # Dá para consultar se uma escrita enviada foi efetivada? (timeout após envio = resultado
    # desconhecido; com consulta de status, repete-se só o que comprovadamente não ocorreu)
    status_query: bool = False
    reconciliation: str = ""  # como resolver resultado desconhecido sem idempotência nem consulta
    covered_by: list[str] = Field(min_length=1)  # AC/NFR/EVAL desta spec que testam a falha

    @model_validator(mode="after")
    def _retry_seguro(self):
        unsafe = self.side_effects and not self.idempotent
        if self.retry.max_attempts > 1 and unsafe and not self.status_query:
            raise ValueError(
                "retry em operação com efeito colateral, não idempotente e sem consulta de status "
                "pode duplicar a transação: torne-a idempotente (chave de idempotência), declare "
                "status_query: true ou use max_attempts: 1")
        if unsafe and not self.status_query and not self.reconciliation.strip():
            raise ValueError(
                "escrita não idempotente e sem consulta de status: um timeout após o envio deixa o "
                "resultado desconhecido; declare `reconciliation` (como e quem resolve)")
        return self


class CostCeiling(Strict):
    value: float = Field(gt=0)
    unit: str = Field(min_length=1)  # BRL, USD, tokens, GPU-s...
    window: str = Field(min_length=1)  # por execução, por dia, por tenant/mês...


class Limits(Strict):
    """Limites de cada unidade de trabalho do agente (N-03, N-07). Nada ilimitado."""
    deadline_s: int = Field(ge=1)
    max_steps: int = Field(ge=1)  # iterações do loop do agente
    max_tool_calls: int = Field(ge=0)
    max_input_tokens: int | None = Field(None, ge=1)
    max_output_tokens: int | None = Field(None, ge=1)
    concurrency: int | None = Field(None, ge=1)  # execuções simultâneas por principal/tenant
    cost_ceiling: CostCeiling | None = None


class Design(Strict):
    numbers: list[Number] = Field(min_length=1)
    data_flow: DataFlow
    alternatives: list[Alternative] = Field(min_length=2)
    risks: list[Risk] = Field(min_length=1)
    # Obrigatório declarar, mesmo vazio: `dependencies: []` afirma que não há dependência externa.
    dependencies: list[Dependency]
    # Obrigatório quando o projeto usa o perfil de agentes (specs/agents.yaml).
    limits: Limits | None = None

    @model_validator(mode="after")
    def _uma_escolhida(self):
        n = sum(a.chosen for a in self.alternatives)
        if n != 1:
            raise ValueError(f"exatamente uma alternativa deve ter chosen: true (encontradas {n})")
        return self


# --- Evals: comportamento não determinístico (LLM) ------------------------------

EVAL_PATTERN = r"^EVAL-\d{3,}$"


class Threshold(Strict):
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def _limite(self):
        if self.min is None and self.max is None:
            raise ValueError("informe min e/ou max")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min maior que max")
        return self


class Eval(Strict):
    """Critério estatístico sobre um dataset versionado. O harness grava resultados brutos
    por caso e execução; o sdd calcula os agregados (o harness não declara a nota)."""
    id: str = Field(pattern=EVAL_PATTERN)
    metric: str = Field(min_length=1)
    description: str = ""
    dataset: ProjectPath = Field(min_length=1)  # JSONL no repo, cada linha com "id" único
    min_cases: int = Field(ge=1)  # casos distintos exigidos em CADA execução
    runs: int = Field(3, ge=1)  # execuções independentes (o LLM varia entre elas)
    aggregate: Literal["pass_rate", "mean_score"] = "pass_rate"
    threshold: Threshold
    max_run_spread: float | None = Field(None, ge=0)  # maior - menor valor entre execuções
    use_lower_bound: bool = False  # compara o limite inferior do IC 95% (Wilson), não a média
    judge: Literal["deterministic", "llm"] = "deterministic"
    # Crítico: um único caso falho em qualquer execução reprova (ex.: violação de autorização),
    # independentemente da média. Só para pass_rate.
    critical: bool = False

    @model_validator(mode="after")
    def _coerencia(self):
        if self.use_lower_bound and self.aggregate != "pass_rate":
            raise ValueError("use_lower_bound só vale para aggregate: pass_rate")
        if self.critical and self.aggregate != "pass_rate":
            raise ValueError("critical só vale para aggregate: pass_rate")
        return self


# --- Arquitetura: regras de dependência entre camadas ---------------------------

ARCH_PATTERN = r"^ARCH-\d{3,}$"


class ArchRule(BaseModel):
    """Arquivos em `from` não podem importar `forbid` (módulos) nem `forbid_paths` (arquivos
    do repo). Ex.: domínio não importa LangGraph, provedor de LLM nem a camada de infra."""
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=ARCH_PATTERN)
    description: str = Field(min_length=1)
    sources: list[str] = Field(alias="from", min_length=1)  # globs dos arquivos sujeitos à regra
    forbid: list[str] = []  # módulos: "openai", "langchain*", "@langchain/core", "myapp.infra"
    forbid_paths: list[str] = []  # arquivos do repo alcançados por import relativo: "src/infra/**"

    @model_validator(mode="after")
    def _algo_proibido(self):
        if not self.forbid and not self.forbid_paths:
            raise ValueError("informe forbid e/ou forbid_paths")
        return self


class Architecture(Strict):
    rules: list[ArchRule] = []


# --- Perfil de agentes: catálogo de referência e matriz do projeto -----------------

class CatalogRequirement(Strict):
    id: str = Field(pattern=r"^[A-Z]-\d{2,}$")
    title: str
    requirement: str
    evidence: str
    critical: bool = False


class CatalogModule(Strict):
    name: str
    activate_when: str = ""
    mandatory: bool = False
    requirements: list[CatalogRequirement] = Field(min_length=1)


class Catalog(Strict):
    profile: str
    version: str
    modules: dict[str, CatalogModule]


ModuleStatus = Literal["ativo", "inativo", "pendente"]


class ModuleState(Strict):
    status: ModuleStatus
    reason: str = ""


class NotApplicable(Strict):
    not_applicable: str = Field(min_length=1)


class AgentsProfile(Strict):
    """specs/agents.yaml: quais módulos se aplicam e o que prova cada requisito."""
    profile: Literal["agentes"]
    # local: pendências viram aviso. piloto/producao: pendência reprova; producao exige módulo P.
    stage: Literal["local", "piloto", "producao"] = "local"
    modules: dict[str, ModuleStatus | ModuleState]
    coverage: dict[str, list[str] | NotApplicable] = {}

    def state(self, key: str) -> ModuleState | None:
        v = self.modules.get(key)
        return ModuleState(status=v) if isinstance(v, str) else v


# --- Escopo: premissas, perguntas, decisões -------------------------------------

AD_PATTERN = r"^AD-\d{3,}$"
Size = Literal["small", "medium", "large", "complex"]


class Assumption(Strict):
    """Lacuna da spec resolvida por um padrão escolhido, com justificativa."""
    assumption: str = Field(min_length=1)
    chosen: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class OpenQuestion(Strict):
    """Pergunta sem `answer` bloqueia o `sdd validate` (closure gate)."""
    question: str = Field(min_length=1)
    answer: str = ""


class Decision(Strict):
    id: str = Field(pattern=AD_PATTERN)
    title: str = Field(min_length=1)
    status: Literal["active", "superseded"] = "active"
    decision: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    superseded_by: str | None = Field(None, pattern=AD_PATTERN)

    @model_validator(mode="after")
    def _substituicao(self):
        if self.status == "superseded" and not self.superseded_by:
            raise ValueError("decisão superseded precisa de `superseded_by`")
        if self.status == "active" and self.superseded_by:
            raise ValueError("decisão active não pode ter `superseded_by`")
        return self


class DecisionLog(Strict):
    decisions: list[Decision] = []


# --- Spec e config ------------------------------------------------------------

# --- Tarefas e constituição -------------------------------------------------------

TASK_PATTERN = r"^T-\d{2,}$"
CONST_PATTERN = r"^CONST-\d{2,}$"


class Task(Strict):
    """Unidade pequena e verificável de trabalho, com origem e evidência explícitas."""
    id: str = Field(pattern=TASK_PATTERN)  # única dentro da spec
    title: str = Field(min_length=1)
    origin: list[str] = Field(min_length=1)  # REQ/AC/NFR/EVAL desta spec, ARCH ou CONST
    depends_on: list[str] = []
    done_when: str = Field(min_length=1)  # critério de conclusão observável
    evidence: list[str] = []  # AC/NFR/EVAL/ARCH que provam a conclusão
    status: Literal["todo", "doing", "done"] = "todo"

    @model_validator(mode="after")
    def _concluida_tem_evidencia(self):
        if self.status == "done" and not self.evidence:
            raise ValueError("tarefa done precisa de `evidence` (AC/NFR/EVAL/ARCH que provam a conclusão)")
        return self


ENFORCERS_KIT = ("validate", "check", "design", "limits", "dependencies", "tasks", "diff", "mutate",
                 "eval", "arch", "profile")


class Principle(Strict):
    id: str = Field(pattern=CONST_PATTERN)
    rule: str = Field(min_length=1)
    # O que cobra a regra: ARCH-NNN, AC/NFR/EVAL, gate:<nome>, kit:<recurso>, profile:<requisito>.
    enforced_by: list[str] = []
    manual: str = ""  # quando nada automático cobra: o procedimento de revisão

    @model_validator(mode="after")
    def _cobranca(self):
        if not self.enforced_by and not self.manual.strip():
            raise ValueError("princípio precisa de `enforced_by` ou de `manual` (como é revisado)")
        return self


class Constitution(Strict):
    principles: list[Principle] = Field(min_length=1)


class Spec(Strict):
    feature: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: int = Field(ge=1)
    # Tamanho define o rigor exigido. Padrão "large": esquecer o campo nunca afrouxa a regra.
    size: Size = "large"
    summary: str = ""
    out_of_scope: list[str] = []
    assumptions: list[Assumption] = []
    open_questions: list[OpenQuestion] = []
    decisions: list[str] = []  # AD-NNN de specs/decisions.yaml que esta feature segue
    requirements: list[Requirement] = Field(min_length=1)
    design: Design | None = None
    evals: list[Eval] = []
    tasks: list[Task] = []
    invariants: list[str] = []
    quality_gates: list[str] = []
    # Código que pertence a esta feature (globs com **). Usado por `sdd diff`.
    paths: list[str] = []

    def criteria(self) -> list[tuple[str, str, str]]:
        """(id, origem, descrição) de tudo que exige evidência de teste."""
        out = [(a.id, r.id, a.then + (f" — proibido: {'; '.join(a.forbidden)}" if a.forbidden else ""))
               for r in self.requirements for a in r.acceptance]
        if self.design:
            out += [(n.id, "design", n.describe()) for n in self.design.numbers if n.id]
        return out


class TestsConfig(Strict):
    command: str
    junit: ProjectPath
    timeout: int = Field(3600, ge=1)  # segundos; vale para testes e gates
    # Onde ficam os testes (para o `sdd diff` reconhecer um teste de regressão em SDD-Fix).
    paths: list[str] = ["tests/**", "test/**", "**/test_*.py", "**/*_test.py", "**/*_test.go",
                        "**/*.test.*", "**/*.spec.*", "**/src/test/**"]


class Config(Strict):
    version: int = 1
    tests: TestsConfig
    gates: dict[str, str] = {}
    # O que conta como código de produção. Arquivo aqui sem feature dona reprova o `sdd diff`.
    code: list[str] = []
    # Migração: o trailer sem feature só é aceito com opt-in e aviso de depreciação.
    allow_global_diff_override: bool = False
    # Exige a seção `design` nas specs cujo `size` está em `design_required_for`.
    require_design: bool = False
    design_required_for: list[Size] = ["large", "complex"]
    # Exige `tasks` nas specs com size em tasks_required_for.
    require_tasks: bool = False
    tasks_required_for: list[Size] = ["large", "complex"]
    # Critério vago ("rápido", "seguro", "corretamente") sem valor observável: aviso, ou erro se true.
    strict_criteria: bool = False
    # Feature `small` que altera mais arquivos de código que isto reprova o `sdd diff`.
    small_max_files: int = Field(3, ge=1)
    mutation: MutationConfig = Field(default_factory=lambda: MutationConfig())
    evals: EvalsConfig = Field(default_factory=lambda: EvalsConfig())


class EvalsConfig(Strict):
    # Roda o harness. Ele grava <results_dir>/<EVAL-ID>.jsonl, uma linha por caso e execução:
    # {"case": "<id do dataset>", "run": 1, "pass": true}   ou   {..., "score": 0.82}
    command: str | None = None
    results_dir: ProjectPath = ".sdd/evals"
    timeout: int = Field(3600, ge=1)
    # Política do projeto: evals com judge: llm só são aceitas se isto for true.
    allow_llm_judge: bool = False


class MutationConfig(Strict):
    command: str | None = None  # padrão: tests.command (dica: falhar rápido, ex. pytest -x)
    min_score: float = Field(0.8, ge=0, le=1)
    max_mutants: int = Field(50, ge=1)
    timeout: int = Field(120, ge=1)  # segundos por mutante; estouro conta como morto
    extensions: list[str] = [".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".kt",
                             ".cs", ".rb", ".php", ".rs", ".c", ".cc", ".cpp", ".swift", ".scala"]
    # Diretórios pesados que a cópia isolada referencia por symlink em vez de copiar.
    link: list[str] = ["node_modules", ".venv", "venv"]
    # Variáveis de ambiente para os testes na cópia; {root} vira o caminho da cópia.
    # Ex.: PYTHONPATH: "{root}/src" quando o pacote está instalado em modo editável.
    env: dict[str, str] = {}


Config.model_rebuild()


def eval_ids(spec: Spec) -> list[str]:
    return [e.id for e in spec.evals]
