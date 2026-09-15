"""Command-line entry point: python -m aig <command>."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import ROOT
from .compare import axis_coverage, nearest_neighbours, vocabulary_usage
from .export import build_site_data, inline_into_html
from .records import load_cards, load_executions, select, validate_cards, validate_executions


def cmd_validate(_: argparse.Namespace) -> int:
    cards = load_cards()
    rep = validate_cards(cards)
    print("benchmark cards:", rep.summary())
    rows = load_executions()
    rep2 = validate_executions(rows, cards)
    print("execution records:", rep2.summary())
    return 0 if rep.ok and rep2.ok else 1


def cmd_report(args: argparse.Namespace) -> int:
    cards = load_cards()
    scope = getattr(args, "scope", "core")
    bench = select(cards, scope)
    n_core = len(select(cards, "core"))
    print(f"{len(cards)} cards; {n_core} in the core analysis set, {len(cards) - n_core} held as reference")
    print(f"reporting on scope={scope} ({len(bench)} cards)\n")
    cov = axis_coverage(cards, scope)
    print("Axis coverage (number of benchmarks covering each axis):")
    for a in cov["axes"]:
        bar = "#" * a["n_covering"]
        print(f"  {a['id']:<24} {a['n_covering']:>3}  {bar}")
    print("\nGaps (no benchmark covers):", ", ".join(cov["gaps"]) or "none")
    print("Rare (<=2 benchmarks):", ", ".join(cov["rare"]) or "none")
    print("\nNearest neighbours (Gower distance over all schema features):")
    for rid, nn in nearest_neighbours(bench, k=2).items():
        print(f"  {rid:<36} -> " + ", ".join(f"{j} ({d:.2f})" for j, d in nn))
    print("\nVocabulary values never used (candidates to prune or document):")
    for key, cnt in vocabulary_usage(cards).items():
        unused = [v for v, n in cnt.items() if n == 0]
        if unused:
            print(f"  {key}: {', '.join(unused)}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    written = build_site_data()
    for name, p in written.items():
        print("wrote", p.relative_to(ROOT))
    if args.standalone:
        out = inline_into_html(ROOT / "site" / "index.html")
        print("wrote", out.relative_to(ROOT))
    return 0


def cmd_matrix(args: argparse.Namespace) -> int:
    from .compare import distance_matrix
    cards = select(load_cards(), args.scope)
    ids, mat = distance_matrix(cards, group=args.group)
    if args.format == "json":
        json.dump({"ids": ids, "matrix": mat}, sys.stdout, indent=1)
        return 0
    w = max(len(i) for i in ids)
    print(" " * w, *[i[:6].rjust(6) for i in ids])
    for i, row in zip(ids, mat):
        print(i.ljust(w), *[("   -  " if v is None else f"{v:6.2f}") for v in row])
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aig", description="agentic-instrument-gym tooling")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="validate all cards and execution records against the schemas").set_defaults(fn=cmd_validate)
    rp = sub.add_parser("report", help="print axis coverage, gaps, nearest neighbours")
    rp.add_argument("--scope", choices=["core", "reference", "all"], default="core", help="which cards to analyse (default: the core benchmark set)")
    rp.set_defaults(fn=cmd_report)
    e = sub.add_parser("export", help="write site/data/*.json for the explorer")
    e.add_argument("--standalone", action="store_true", help="also write site/index.standalone.html with data inlined")
    e.set_defaults(fn=cmd_export)
    m = sub.add_parser("matrix", help="print the Gower distance matrix")
    m.add_argument("--group", choices=["benchmark", "task", "sample_environment", "agent"], default=None)
    m.add_argument("--scope", choices=["core", "reference", "all"], default="core")
    m.add_argument("--format", choices=["text", "json"], default="text")
    m.set_defaults(fn=cmd_matrix)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
