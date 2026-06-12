#!/usr/bin/env python3
"""Deterministic TAM/SAM/SOM model builder.

Bottom-up: TAM = entities * ACV, SAM = TAM * sam_frac, SOM = SAM * som_frac.
Writes an .xlsx (via openpyxl) with Assumptions + Sizing sheets, or falls back
to .csv if openpyxl is missing. Prints the computed figures as JSON to stdout so
the calling agent can read them back deterministically.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def compute(entities: float, acv: float, sam_frac: float, som_frac: float) -> dict:
    tam = entities * acv
    sam = tam * sam_frac
    som = sam * som_frac
    return {"tam_usd": tam, "sam_usd": sam, "som_usd": som}


def write_xlsx(path: Path, assumptions: dict, sizing: dict) -> bool:
    try:
        from openpyxl import Workbook
    except ImportError:
        return False

    wb = Workbook()
    a = wb.active
    a.title = "Assumptions"
    a.append(["key", "value"])
    for k, v in assumptions.items():
        a.append([k, v])

    s = wb.create_sheet("Sizing")
    s.append(["metric", "value_usd"])
    for k, v in sizing.items():
        s.append([k.replace("_usd", "").upper(), v])

    wb.save(path)
    return True


def write_csv(path: Path, assumptions: dict, sizing: dict) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["section", "key", "value"])
        for k, v in assumptions.items():
            w.writerow(["assumption", k, v])
        for k, v in sizing.items():
            w.writerow(["sizing", k, v])


def main() -> None:
    p = argparse.ArgumentParser(description="Build a TAM/SAM/SOM model.")
    p.add_argument("--entities", type=float, required=True, help="# target buyers")
    p.add_argument("--acv", type=float, required=True, help="annual contract value (USD)")
    p.add_argument("--sam-frac", type=float, default=0.20, help="SAM as fraction of TAM")
    p.add_argument("--som-frac", type=float, default=0.01, help="SOM as fraction of SAM")
    p.add_argument("--out", type=Path, default=Path("tam_model.xlsx"))
    args = p.parse_args()

    assumptions = {
        "target_entities": args.entities,
        "acv_usd": args.acv,
        "sam_fraction": args.sam_frac,
        "som_fraction": args.som_frac,
    }
    sizing = compute(args.entities, args.acv, args.sam_frac, args.som_frac)

    out = args.out
    if not write_xlsx(out, assumptions, sizing):
        out = out.with_suffix(".csv")
        write_csv(out, assumptions, sizing)

    print(json.dumps({**sizing, "model_path": str(out)}, indent=2))


if __name__ == "__main__":
    main()
