"""Compare this environment's offline projections with a reference CSV.

Temporary diagnostic for the CI golden mismatch: prints every row/column
whose rounded value differs from tests/golden/_probe_local.csv, plus the
worst absolute difference, so the divergence between environments can be
located exactly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tools.selfcheck import projection_frame  # noqa: E402

REF = ROOT / "tests" / "golden" / "_probe_local.csv"


def main():
    ref = pd.read_csv(REF)
    from fplbot import model
    df, teams, fx, gws = model.build(horizon=5, start_gw=3)
    cur = projection_frame(df, gws)

    print("env:", f"{np.__version__=} {pd.__version__=}")
    print("same shape:", ref.shape == cur.shape)
    same_cols = list(ref.columns) == list(cur.columns)
    print("same columns:", same_cols)
    if ref.shape != cur.shape or not same_cols:
        return
    pos = ref["id"].to_numpy() == cur["id"].to_numpy()
    print("ids aligned:", bool(pos.all()))

    differing = []
    for c in list(cur.columns)[1:]:
        r = pd.to_numeric(ref[c], errors="coerce").to_numpy(dtype=float)
        s = pd.to_numeric(cur[c], errors="coerce").to_numpy(dtype=float)
        d = s - r
        nz = np.nonzero(~(np.isnan(d) | (d == 0)))[0]
        if nz.size:
            differing.append((c, [(int(cur["id"].iloc[i]), str(cur["name"].iloc[i]),
                                   float(r[i]), float(s[i])) for i in nz[:6]],
                              float(np.nanmax(np.abs(d)))))
    if not differing:
        print("no value differs from the reference CSV")
    for c, examples, worst in differing:
        print(f"column {c}: worst |diff| {worst:.6f}, e.g. {examples}")
    print("columns differing:", [c for c, _, _ in differing])


if __name__ == "__main__":
    main()