from __future__ import annotations

import json
from pathlib import Path

import typer

from . import core
from .models import Spec
from .scaffold import FILES

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="SDD agnóstico: specs como contrato, verificação fora do LLM.")
Root = typer.Option(Path("."), "--root", "-C", help="Raiz do projeto.")


@app.command()
def init(root: Path = Root):
    """Cria a estrutura specs/, AGENTS.md e o workflow de CI (não sobrescreve)."""
    for rel, content in FILES.items():
        p = root / rel
        if p.exists():
            typer.echo(f"mantido  {rel}")
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        typer.echo(f"criado   {rel}")


def _load_or_exit(root: Path) -> core.Project:
    proj = core.load(root)
    if proj.errors:
        for e in proj.errors:
            typer.echo(f"ERRO  {e}", err=True)
        raise typer.Exit(1)
    return proj


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
def check(root: Path = Root):
    """Roda testes e gates; falha se algum AC não tiver teste passando."""
    proj = _load_or_exit(root)
    report = core.check(proj)
    md = core.write_report(proj, report)
    for r in report["criteria"]:
        typer.echo(f"{r['verdict']:<10} {r['id']:<8} {r['feature']}: {r['text']}")
    for g in report["gates"]:
        typer.echo(f"{'OK' if g['ok'] else 'FALHOU':<10} gate {g['gate']}")
    for p in report["problems"]:
        typer.echo(f"ERRO  {p}", err=True)
    typer.echo(f"\n{'APROVADO' if report['ok'] else 'REPROVADO'} — relatório em {md}")
    raise typer.Exit(0 if report["ok"] else 1)


@app.command()
def diff(
    base: str = typer.Option("origin/main", "--base", "-b", help="Ref de comparação (branch alvo do PR)."),
    root: Path = Root,
):
    """Reprova quando código de uma feature muda sem a spec mudar junto.

    Refatoração sem mudança de comportamento: adicione ao commit o trailer
    `SDD-No-Spec-Change: <motivo>`. Fica registrado no histórico do git.
    """
    from .diff import GitError, changes, evaluate

    proj = _load_or_exit(root)
    try:
        changed, messages = changes(root, base)
    except GitError as exc:
        typer.echo(f"ERRO  {exc}", err=True)
        raise typer.Exit(2)
    res = evaluate(proj, changed, messages)
    for w in res.warnings:
        typer.echo(f"AVISO {w}")
    for v in res.violations:
        typer.echo(f"ERRO  {v}", err=True)
    typer.echo(f"\n{len(changed)} arquivo(s) alterado(s) desde {base} — "
               f"{'APROVADO' if res.ok else 'REPROVADO'}")
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

    proj = _load_or_exit(root)
    only = None
    if base:
        from .diff import GitError, changes
        try:
            only = set(changes(root, base)[0])
        except GitError as exc:
            typer.echo(f"ERRO  {exc}", err=True)
            raise typer.Exit(2)
    specs = [s for s in proj.specs.values() if s.paths and (feature is None or s.feature == feature)]
    if not specs:
        typer.echo("ERRO  nenhuma feature com `paths` para mutar", err=True)
        raise typer.Exit(2)

    reports = []
    for spec in specs:
        typer.echo(f"\n== {spec.feature}")
        rep = mutation.run_feature(
            proj, spec, only, max_mutants,
            on_result=lambda m: typer.echo(f"  {m.status:<9} {m.where:<28} {m.operator}"))
        reports.append(rep)
        if rep.error:
            typer.echo(f"  ERRO  {rep.error}", err=True)
        elif rep.mutants:
            if rep.killed == 0:
                typer.echo("  AVISO nenhum mutante morreu: os testes estão rodando contra a cópia? "
                           "(pacote editável → mutation.env PYTHONPATH: \"{root}/src\")")
            typer.echo(f"  score {rep.score:.0%} (mínimo {rep.min_score:.0%})")
        else:
            typer.echo("  nada para mutar")

    d = root / ".sdd"
    d.mkdir(exist_ok=True)
    (d / "mutation.md").write_text(mutation.render_markdown(reports), encoding="utf-8")
    (d / "mutation.json").write_text(json.dumps([
        {"feature": r.feature, "score": r.score, "min_score": r.min_score, "ok": r.ok,
         "error": r.error, "candidates": r.candidates,
         "mutants": [vars(m) for m in r.mutants]} for r in reports
    ], indent=2, ensure_ascii=False), encoding="utf-8")

    if any(r.error for r in reports):
        raise typer.Exit(2)
    ok = all(r.ok for r in reports)
    typer.echo(f"\n{'APROVADO' if ok else 'REPROVADO'} — relatório em {d / 'mutation.md'}")
    raise typer.Exit(0 if ok else 1)


@app.command(name="eval")
def eval_cmd(root: Path = Root):
    """Roda o harness de evals e aplica os critérios estatísticos (EVAL-NNN).

    Separado do `check` porque evals costumam chamar APIs de LLM (custo e tempo).
    """
    from . import evals

    proj = _load_or_exit(root)
    report = evals.run(proj)
    d = root / ".sdd"
    d.mkdir(exist_ok=True)
    (d / "eval.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (d / "eval.md").write_text(evals.render_markdown(report), encoding="utf-8")
    if not report["evals"] and report["ok"]:
        typer.echo("nenhuma eval declarada nas specs")
        raise typer.Exit(0)
    for r in report["evals"]:
        val = f"{r['value']:.3f}" if "value" in r else "—"
        tag = " [juiz LLM]" if r["judge"] == "llm" else ""
        typer.echo(f"{r['verdict']:<15} {r['id']:<9} {r['metric']} = {val}{tag}"
                   + (f"  ({r['detail']})" if r["detail"] else ""))
    for p in report["problems"]:
        typer.echo(f"ERRO  {p}", err=True)
    typer.echo(f"\n{'APROVADO' if report['ok'] else 'REPROVADO'} — relatório em {d / 'eval.md'}")
    raise typer.Exit(0 if report["ok"] else 1)


@app.command()
def schema():
    """Imprime o JSON Schema da spec (para editores e outras ferramentas)."""
    typer.echo(json.dumps(Spec.model_json_schema(), indent=2, ensure_ascii=False))
