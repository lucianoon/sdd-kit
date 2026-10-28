from __future__ import annotations

import json
from pathlib import Path

import typer
from typer.core import TyperGroup

from . import core
from .models import Spec
from .artifacts import ArtifactError


class SafeGroup(TyperGroup):
    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except ArtifactError as exc:
            _err(str(exc))
            raise typer.Exit(2)

app = typer.Typer(cls=SafeGroup, add_completion=False, no_args_is_help=True,
                  help="SDD agnóstico: specs como contrato, verificação fora do LLM.")
Root = typer.Option(Path("."), "--root", "-C", help="Raiz do projeto.")


def _err(msg: str) -> None:
    typer.secho(f"ERRO  {msg}", fg=typer.colors.RED, err=True)


def _warn(msg: str, err: bool = False) -> None:
    typer.secho(f"AVISO {msg}", fg=typer.colors.YELLOW, err=err)


def _verdict(ok: bool, tail: str) -> None:
    """Linha final de um comando. Cores só em terminal; no CI a saída sai limpa."""
    typer.echo("")
    typer.secho("APROVADO" if ok else "REPROVADO", fg=typer.colors.GREEN if ok else typer.colors.RED,
                bold=True, nl=False)  # sdd: no-mutate (cores: mudança só de apresentação)
    typer.echo(f" — {tail}" if tail else "")


VERDICT_COLORS = {"OK": typer.colors.GREEN, "killed": typer.colors.GREEN, "timeout": typer.colors.GREEN,
                  "survived": typer.colors.RED}


def _row(status: str, rest: str, width: int = 10) -> None:
    color = VERDICT_COLORS.get(status, typer.colors.RED if status.isupper() else None)
    typer.secho(f"{status:<{width}}", fg=color, nl=False)
    typer.echo(f" {rest}")


def _version(value: bool):
    if value:
        from . import __version__
        typer.echo(f"sdd-kit {__version__}")
        raise typer.Exit()


@app.callback()
def main(version: bool = typer.Option(False, "--version", callback=_version, is_eager=True,
                                      help="Mostra a versão e sai.")):
    """SDD agnóstico: specs como contrato, verificação fora do LLM."""


@app.command()
def init(
    root: Path = Root,
    preset: str = typer.Option("minimo", "--preset", help="minimo | padrao | completo"),
    profile: str = typer.Option(None, "--profile", "-p", help="Perfil de requisitos (disponível: agentes)."),
):
    """Cria a estrutura mínima (ou a de um preset). Nunca sobrescreve arquivos existentes.

    minimo: spec, check e diff. padrao: + design, tarefas, constituição, arquitetura e
    decisões. completo: + evals, mutação e critério estrito. Mais tarde: `sdd enable`.
    """
    from .layers import init as do_init

    try:
        actions = do_init(root, preset, profile)
    except ValueError as exc:
        _err(str(exc))
        raise typer.Exit(2)
    for a in actions:
        typer.echo(a)
    typer.echo("\nPróximo passo: `sdd specify <nome>` e depois `sdd validate`.")


@app.command()
def enable(
    layers: list[str] = typer.Argument(..., help="design tasks constitution arch decisions approval evals mutate strict agentes"),
    root: Path = Root,
):
    """Liga camadas num projeto existente: cria arquivos, ajusta a config e o AGENTS.md."""
    from .layers import apply_layer

    for layer in layers:
        try:
            for a in apply_layer(root, layer):
                typer.echo(a)
        except ValueError as exc:
            _err(str(exc))
            raise typer.Exit(2)


@app.command()
def specify(
    name: str = typer.Argument(..., help="Nome da feature (minúsculas e hífen), ex.: criar-pedido."),
    size: str = typer.Option("medium", "--size", "-s", help="small | medium | large | complex"),
    acs: int = typer.Option(1, "--acs", help="Quantos critérios de aceitação gerar."),
    touches: str = typer.Option("", "--touches", help="Dimensões de requisito implícito, separadas por "
                                "vírgula: persistencia, autenticacao, pagamentos, chamadas-externas, "
                                "concorrencia, transicoes-de-estado."),
    root: Path = Root,
):
    """Cria o esqueleto de uma spec com IDs livres e as seções que o size exige.

    Os campos a preencher levam o marcador PREENCHER; o `sdd validate` reprova até
    todos serem substituídos por conteúdo real. Com --touches, as perguntas de cada
    dimensão entram em open_questions e bloqueiam o validate até serem respondidas.
    """
    from .specify import SpecifyError, create

    try:
        path, ids = create(root, name, size, acs, tuple(t.strip() for t in touches.split(",") if t.strip()))
    except SpecifyError as exc:
        _err(exc)
        raise typer.Exit(2)
    typer.echo(f"criado   {path.relative_to(root).as_posix()}")
    typer.echo("IDs      " + "  ".join(f"{k}: {v}" for k, v in ids.items()))
    typer.echo(f"\nPróximo passo: troque cada {core.PLACEHOLDER} por conteúdo real e rode `sdd validate`.")


def _load_or_exit(root: Path, as_json: bool = False) -> core.Project:
    proj = core.load(root)
    for w in proj.warnings:
        _warn(w, err=as_json)  # com --json, o stdout leva só o documento
    if proj.errors:
        for e in proj.errors:
            _err(e)
        raise typer.Exit(1)
    return proj


def _constitution(proj, command: str, ok: bool, verdicts=None, complete: bool = True):
    from .analysis import constitution_matrix, kit_context

    if proj.constitution is None:
        return None
    states = kit_context(proj, {})
    if states[command] != "NÃO_APLICÁVEL" or not ok:
        states[command] = "FALHOU" if not ok else ("OK" if complete else "PENDENTE")
    return constitution_matrix(proj.constitution, verdicts or {}, {}, {}, states)


@app.command()
def validate(root: Path = Root):
    """Valida schema, unicidade de IDs e gates referenciados."""
    proj = _load_or_exit(root)
    ids = [c[0] for s in proj.specs.values() for c in s.criteria()]
    n_nfr = sum(i.startswith("NFR-") for i in ids)
    n_design = sum(s.design is not None for s in proj.specs.values())
    typer.echo(f"OK  {len(proj.specs)} spec(s) ({n_design} com design), "
               f"{len(ids) - n_nfr} critério(s) de aceitação, {n_nfr} NFR(s)")


@app.command()
def analyze(
    root: Path = Root,
    as_json: bool = typer.Option(False, "--json", help="Emite JSON no stdout, inclusive com erros estáticos."),
):
    """Analisa declarações e rastreabilidade; grava .sdd/analyze.json e .md, sem rodar testes."""
    from .report import write_command_report
    from .review import analyze as do_analyze, render_markdown

    report = do_analyze(core.load(root))
    md = render_markdown(report)
    write_command_report(root, "analyze", report, md)
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False) if as_json else md)
    raise typer.Exit(0 if report["ok"] else 1)


@app.command()
def guide(
    feature: str = typer.Argument(..., help="Nome exato da feature declarada na spec."),
    stage: str = typer.Option("clarify", "--stage", help="clarify | plan | implement | converge | resume"),
    root: Path = Root,
    as_json: bool = typer.Option(False, "--json", help="Emite contexto estruturado em JSON."),
):
    """Prepara contexto para o agente. Não grava arquivos nem executa comandos do projeto."""
    from .workflow import build, render_markdown

    try:
        packet = build(core.load(root), feature, stage)
    except ValueError as exc:
        _err(str(exc))
        raise typer.Exit(2)
    typer.echo(json.dumps(packet, indent=2, ensure_ascii=False) if as_json else render_markdown(packet))
    raise typer.Exit(1 if packet["status"] == "BLOQUEADO" else 0)


@app.command()
def approve(
    feature: str = typer.Argument(..., help="Nome exato da feature declarada na spec."),
    stage: str = typer.Option("spec", "--stage", help="spec (requisitos e escopo) | plan (design e tarefas)"),
    by: str = typer.Option(..., "--by", help="Quem aprovou."),
    quote: str = typer.Option(..., "--quote", help="As palavras de quem aprovou, sem paráfrase."),
    root: Path = Root,
):
    """Registra na spec a aprovação humana de uma etapa, com o hash do conteúdo aprovado.

    Declaração, não evidência: o kit não autentica quem aprovou, e o check continua decidindo
    o que está pronto. Mudar o conteúdo da etapa depois deixa a aprovação desatualizada.
    """
    from .approvals import ApprovalError, approve as do_approve

    try:
        rel, approval = do_approve(core.load(root), feature, stage, by, quote)
    except ApprovalError as exc:
        _err(str(exc))
        raise typer.Exit(2)
    typer.echo(f"aprovado {stage} de {feature} por {approval.by} em {approval.date.isoformat()}")
    typer.echo(f"hash     {approval.digest}")
    typer.echo(f"gravado  {rel}")


@app.command()
def check(root: Path = Root):
    """Roda testes e gates; falha se algum AC não tiver teste passando."""
    proj = _load_or_exit(root)
    report = core.check(proj)
    md = core.write_report(proj, report)
    for r in report["criteria"]:
        _row(r["verdict"], f"{r['id']:<8} {r['feature']}: {r['text']}")
    for g in report["gates"]:
        _row("OK" if g["ok"] else "FALHOU", f"gate {g['gate']}")
    for p in report["problems"]:
        _err(p)
    _verdict(report["ok"], f"relatório em {md}")
    raise typer.Exit(0 if report["ok"] else 1)


@app.command()
def diff(
    base: str = typer.Option("origin/main", "--base", "-b", help="Ref de comparação (branch alvo do PR)."),
    root: Path = Root,
):
    """Reprova quando código de uma feature muda sem a spec mudar junto.

    Refatoração sem mudança de comportamento: adicione ao commit o trailer
    `SDD-No-Spec-Change(feature): <motivo>`. Fica registrado no histórico do git.
    """
    from .diff import GitError, changes, evaluate, report as diff_report, render_markdown
    from .report import write_command_report

    proj = _load_or_exit(root)
    try:
        changed, messages, merge_base = changes(root, base)
    except GitError as exc:
        _err(exc)
        raise typer.Exit(2)
    res = evaluate(proj, changed, messages, merge_base)
    rep = diff_report(res, base, _constitution(proj, "diff", res.ok))
    write_command_report(root, "diff", rep, render_markdown(rep))
    for w in res.warnings:
        _warn(w)
    for v in res.violations:
        _err(v)
    _verdict(res.ok, f"{len(changed)} arquivo(s) alterado(s) desde {base}")
    raise typer.Exit(0 if res.ok else 1)


@app.command()
def mutate(
    feature: str = typer.Option(None, "--feature", "-f", help="Só esta feature."),
    base: str = typer.Option(None, "--base", "-b", help="Só arquivos alterados desde esta ref."),
    max_mutants: int = typer.Option(None, "--max", help="Sobrescreve mutation.max_mutants."),
    root: Path = Root,
):
    """Injeta falhas no código das features e cobra que os testes as detectem.

    Roda numa cópia isolada; o diretório de trabalho nunca é alterado.
    """
    from . import mutation
    from .report import metadata, write_command_report

    proj = _load_or_exit(root)
    only = None
    if base:
        from .diff import GitError, changes
        try:
            only = set(changes(root, base)[0])
        except GitError as exc:
            _err(exc)
            raise typer.Exit(2)
    specs = [s for s in proj.specs.values() if s.paths and (feature is None or s.feature == feature)]
    if not specs:
        _err("nenhuma feature com `paths` para mutar")
        raise typer.Exit(2)

    reports = []
    for spec in specs:
        typer.echo(f"\n== {spec.feature}")
        rep = mutation.run_feature(
            proj, spec, only, max_mutants,
            on_result=lambda m: _row(m.status, f"{m.where:<28} {m.operator}", 9))
        reports.append(rep)
        if rep.error:
            _err(rep.error)
        elif rep.mutants:
            if rep.killed == 0:
                _warn("nenhum mutante morreu: os testes estão rodando contra a cópia? "
                      "(pacote editável → mutation.env PYTHONPATH: \"{root}/src\")")
            typer.echo(f"  score {rep.score:.0%} (mínimo {rep.min_score:.0%})")
        else:
            typer.echo("  nada para mutar")

    ok = all(r.ok for r in reports)
    complete = feature is None and base is None and all(r.mutants for r in reports)
    const = _constitution(proj, "mutate", ok, complete=complete)
    scope = {"features": [r.feature for r in reports], "base": base,
             "max_mutants": max_mutants or proj.config.mutation.max_mutants}
    data = [
        {**metadata("mutate"), "scope": scope, "constitution": const,
         "feature": r.feature, "verdict": r.verdict, "score": r.score, "min_score": r.min_score, "ok": r.ok,
         "error": r.error, "candidates": r.candidates,
         "mutants": [vars(m) for m in r.mutants]} for r in reports
    ]
    md = write_command_report(root, "mutation", data, mutation.render_markdown(reports, const, scope))

    if any(r.error for r in reports):
        raise typer.Exit(2)
    _verdict(ok, f"relatório em {md}")
    raise typer.Exit(0 if ok else 1)


@app.command(name="profile")
def profile_cmd(
    root: Path = Root,
    show_catalog: bool = typer.Option(False, "--catalog", help="Lista o catálogo completo de requisitos."),
):
    """Mostra a matriz do perfil de agentes: módulos, requisitos e evidências declaradas."""
    from .profile import AGENTS_PATH, catalog, matrix

    if show_catalog:
        for key, mod in catalog().modules.items():
            typer.echo(f"\n{key} — {mod.name}{' (obrigatório)' if mod.mandatory else ''}")
            typer.echo(f"   ative quando: {' '.join(mod.activate_when.split())}")
            for r in mod.requirements:
                typer.echo(f"   {r.id}{'*' if r.critical else ' '} {r.title}: {r.requirement}")
                typer.echo(f"         evidência: {r.evidence}")
        typer.echo("\n(*) crítico: exige AC, NFR ou ARCH e não aceita not_applicable")
        raise typer.Exit(0)
    proj = core.load(root)
    if proj.agents is None:
        _err(f"{AGENTS_PATH} ausente ou inválido (crie com `sdd enable agentes`)")
        for e in proj.errors:
            _err(e)
        raise typer.Exit(2)
    typer.echo(f"estágio: {proj.agents.stage}")
    for r in matrix(proj, proj.agents, {}):
        ev = ", ".join(e["id"] for e in r["evidence"])
        star = "*" if r["critical"] else " "
        state = "DECLARADO" if r["state"] == "COBERTO" else r["state"]
        typer.echo(f"  {r['id']}{star} {state:<14} {r['title']}" + (f"  [{ev}]" if ev else ""))
    for w in proj.warnings:
        _warn(w)
    for e in proj.errors:
        _err(e)
    raise typer.Exit(1 if proj.errors else 0)


@app.command(name="arch")
def arch_cmd(root: Path = Root):
    """Verifica só as regras de arquitetura (specs/architecture.yaml). Rápido, sem testes."""
    from . import arch
    from .report import write_command_report

    proj = _load_or_exit(root)
    rep = arch.check(proj)
    from .evidence import architecture_verdicts
    verdicts = architecture_verdicts(rep)
    rep["constitution"] = _constitution(proj, "arch", rep["ok"], verdicts)
    write_command_report(root, "arch", rep, arch.render_markdown(rep))
    if not rep["rules"]:
        typer.echo("nenhuma regra em specs/architecture.yaml")
        raise typer.Exit(0)
    for e in rep["exceptions"]:
        typer.echo(f"EXCEÇÃO {e['rule']}  {e['file']}:{e['line']}  {e['import']}  ({e['reason']})")
    for v in rep["violations"]:
        extra = f"  [{v['detail']}]" if v.get("detail") else ""
        _err(f"{v['rule']}  {v['file']}:{v['line']}  importa '{v['import']}'{extra}")
    for p in rep["problems"]:
        _err(p)
    _verdict(rep["ok"], f"{len(rep['rules'])} regra(s), {rep['files']} arquivo(s)")
    raise typer.Exit(0 if rep["ok"] else 1)


@app.command(name="eval")
def eval_cmd(root: Path = Root):
    """Roda o harness de evals e aplica os critérios estatísticos (EVAL-NNN).

    Separado do `check` porque evals costumam chamar APIs de LLM (custo e tempo).
    """
    from . import evals
    from .report import write_command_report

    proj = _load_or_exit(root)
    report = evals.run(proj)
    report["constitution"] = _constitution(proj, "eval", report["ok"],
                                             {r["id"]: r["verdict"] for r in report["evals"]})
    md = write_command_report(root, "eval", report, evals.render_markdown(report))
    if not report["evals"] and report["ok"]:
        typer.echo("nenhuma eval declarada nas specs")
        raise typer.Exit(0)
    for r in report["evals"]:
        val = f"{r['value']:.3f}" if "value" in r else "—"
        tag = " [juiz LLM]" if r["judge"] == "llm" else ""
        _row(r["verdict"], f"{r['id']:<9} {r['metric']} = {val}{tag}"
             + (f"  ({r['detail']})" if r["detail"] else ""), 15)
    for p in report["problems"]:
        _err(p)
    _verdict(report["ok"], f"relatório em {md}")
    raise typer.Exit(0 if report["ok"] else 1)


@app.command()
def schema():
    """Imprime o JSON Schema da spec (para editores e outras ferramentas)."""
    typer.echo(json.dumps(Spec.model_json_schema(), indent=2, ensure_ascii=False))


@app.command()
def integrate(
    agent: str = typer.Argument(..., help="codex | claude | cursor | all"),
    root: Path = Root,
):
    """Instala entradas locais para as quatro etapas, preservando personalizações."""
    from .integrations import install
    for path in install(root, agent):
        typer.echo(path)


@app.command(name="risk")
def risk_cmd(
    base: str = typer.Option("origin/main", "--base", "-b", help="Ref de comparação (branch alvo do PR)."),
    author: str = typer.Option(None, "--author", help="Autor da mudança, comparado a review.trusted_authors."),
    approvals: int = typer.Option(None, "--approvals", min=0,
                                  help="Aprovações de PESSOAS já dadas; sem isto o resultado é informativo."),
    as_json: bool = typer.Option(False, "--json", help="Imprime o relatório em JSON."),
    root: Path = Root,
):
    """Calcula o piso de risco da mudança e quantas aprovações humanas ela exige.

    O piso vem de review.tiers, dos riscos das specs donas e de specs/. Escalações externas
    (review.escalations) só elevam o tier. Aprovação de agente não conta.
    """
    from .diff import GitError, changes
    from .governance import risk, render_risk
    from .report import write_command_report

    proj = _load_or_exit(root, as_json)
    try:
        changed, _, _ = changes(root, base)
    except GitError as exc:
        _err(exc)
        raise typer.Exit(2)
    rep = risk(proj, changed, author, approvals)
    write_command_report(root, "risk", rep, render_risk(rep))
    if as_json:
        typer.echo(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        for f in rep["files"]:
            _row(f["tier"], f"{f['path']}  ({'; '.join(f['reasons'])})", 7)
        for e in rep["escalations"]["applied"]:
            _warn(f"escalado para {e['tier']} por {e['source']}: {e['reason']}")
        for n in rep["notes"]:
            _warn(n)
        typer.echo(f"\ntier {rep['tier']} (piso {rep['floor']}): "
                   f"{rep['required_approvals']} aprovação(ões) humana(s) exigida(s)")
        if approvals is not None:
            _verdict(rep["ok"], f"{approvals} de {rep['required_approvals']} aprovação(ões) humana(s)")
    raise typer.Exit(0 if rep["ok"] else 1)


@app.command(name="findings")
def findings_cmd(
    as_json: bool = typer.Option(False, "--json", help="Imprime o relatório em JSON."),
    root: Path = Root,
):
    """Valida achados de um revisor LLM externo como evidência probabilística.

    Reprova achado important aberto com consenso, revisão desatualizada, achado repetido
    e rodada acima de review.max_rounds. Não executa o revisor nem aprova a mudança.
    """
    from .governance import findings, render_findings
    from .report import write_command_report

    proj = _load_or_exit(root, as_json)
    rep = findings(proj)
    write_command_report(root, "findings", rep, render_findings(rep))
    if as_json:
        typer.echo(json.dumps(rep, ensure_ascii=False, indent=2))
    elif rep["state"] == "AUSENTE":
        typer.echo(f"nenhum achado de revisor LLM em {rep['source']}")
    else:
        for p in rep["problems"]:
            _err(p)
        _verdict(rep["ok"], "evidência probabilística; não conta como aprovação humana")
    raise typer.Exit(0 if rep["ok"] else 1)


@app.command(name="fixes")
def fixes_cmd(
    base: str = typer.Option(None, "--base", "-b", help="Só commits depois desta ref."),
    root: Path = Root,
):
    """Exporta commits com SDD-Fix como casos para avaliar revisores (JSON)."""
    from .governance import fixes

    proj = _load_or_exit(root, as_json=True)
    rep = fixes(proj, base)
    typer.echo(json.dumps(rep, ensure_ascii=False, indent=2))
    raise typer.Exit(0 if rep["ok"] else 1)


@app.command(name="cite")
def cite_cmd(reference: str = typer.Argument(..., help="arquivo:linha"), root: Path = Root):
    """Produz referência com hash para revisão ou lição (não executa testes)."""
    from .learning import citation
    typer.echo(json.dumps(citation(root, reference).model_dump(), ensure_ascii=False, indent=2))


@app.command(name="adequacy")
def adequacy_cmd(
    action: str = typer.Argument(..., help="template | check"),
    feature: str = typer.Argument(...),
    root: Path = Root,
):
    """Prepara ou valida integridade de uma revisão semântica separada."""
    from .learning import template, adequacy
    if action == "template":
        typer.echo(template(root, feature).relative_to(root.resolve()))
    elif action == "check":
        report = adequacy(root, feature)
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
        raise typer.Exit(0 if report["ok"] else 1)
    else:
        raise ArtifactError("ação precisa ser template ou check")


@app.command(name="lesson")
def lesson_cmd(
    action: str = typer.Argument(..., help="add | accept | list"),
    identity: str = typer.Argument("", help="ID da lição para accept"),
    feature: str = typer.Option("*", "--feature"),
    cause: str = typer.Option("", "--cause"),
    prevention: str = typer.Option("", "--prevention"),
    evidence: list[str] = typer.Option([], "--evidence", help="arquivo:linha; repetível"),
    reviewer: str = typer.Option("", "--reviewer"),
    root: Path = Root,
):
    """Propõe lições com evidências; somente aceitas e atuais entram no guide."""
    from .learning import add_lesson, accept_lesson, lessons
    if action == "add":
        value = add_lesson(root, feature, cause, prevention, evidence).model_dump()
    elif action == "accept":
        accept_lesson(root, identity, reviewer)
        value = {"id": identity, "status": "accepted"}
    elif action == "list":
        value = lessons(root).model_dump()
    else:
        raise ArtifactError("ação precisa ser add, accept ou list")
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


@app.command(name="change")
def change_cmd(
    action: str = typer.Argument(..., help="propose | show | apply | archive"),
    name: str = typer.Argument(...),
    feature: str = typer.Option("", "--feature"),
    reason: str = typer.Option("", "--reason"),
    root: Path = Root,
):
    """Propõe, compara, aplica e arquiva alterações com baseline e check atual.

    archive executa os comandos de teste e gates configurados no projeto.
    """
    from . import changes
    if action == "propose":
        result = changes.propose(root, name, feature, reason)
    elif action == "show":
        value, _, delta = changes.inspect(root, name)
        result = {"change": value.model_dump(), "delta": delta}
    elif action == "apply":
        result = changes.apply(root, name)
    elif action == "archive":
        result = changes.archive(root, name)
    else:
        raise ArtifactError("ação precisa ser propose, show, apply ou archive")
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command(name="import-spec")
def import_spec_cmd(
    source: str = typer.Argument(..., help="Markdown relativo ao projeto"),
    kind: str = typer.Option(..., "--format", help="speckit | openspec"),
    feature: str = typer.Option(..., "--feature"),
    root: Path = Root,
):
    """Importa cenários reconhecidos como rascunho, preservando fonte e lacunas."""
    from .adapters import import_spec
    try:
        report = import_spec(root, source, kind, feature)
    except (OSError, UnicodeError) as exc:
        raise ArtifactError(str(exc)) from exc
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
