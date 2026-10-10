"""Column -> role assignment with the Hungarian algorithm, plus per-column margins.

Score matrix: columns x roles. ``qty``, ``unit``, ``description``, ``catalog``, ``finish`` and
``mfr`` are used at most once per layout. ``notes`` and ``ignore`` may be used by any number of
columns. Header rows ("MFR", "FINISH", ...) add a strong prior. The *margin* of a column is its
assigned role's score minus the best alternative role's score, and feeds field confidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from hwsets.columns.features import ColumnFeatures

UNIQUE_ROLES = ("qty", "unit", "description", "catalog", "finish", "mfr")
MULTI_ROLES = ("notes", "ignore")
ROLES = UNIQUE_ROLES + MULTI_ROLES
HEADER_PRIOR = 0.6
IGNORE_SCORE = 0.12


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    roles: tuple[str, ...]  # one per column
    scores: tuple[dict[str, float], ...]
    margins: tuple[float, ...]


def role_scores(f: ColumnFeatures, position: int, n_cols: int) -> dict[str, float]:
    """Evidence for each role from a column's value distribution (roughly 0..1)."""
    code_like = max(f.mfr, f.finish)
    fill = min(1.0, f.fill / 0.5)  # sparse columns are weaker evidence
    leftish = 1.0 - position / max(n_cols - 1, 1)
    return {
        "qty": f.qty * (1.0 - f.unit) * (1.0 - f.finish) * fill * (0.85 + 0.15 * leftish),
        "unit": f.unit * fill,
        "mfr": f.mfr * (0.4 + 0.6 * fill) * (1.0 - 0.5 * f.finish),
        "finish": f.finish * (0.4 + 0.6 * fill) * (1.0 - 0.5 * f.mfr),
        "catalog": f.catalog * (1.0 - code_like) * (1.0 - f.qty) * fill,
        "description": f.words * (1.0 - code_like) * (1.0 - f.qty) * fill
        * min(1.0, f.mean_tokens / 1.5),
        "notes": 0.25 * f.words * (1.0 - code_like) * f.fill,
        "ignore": IGNORE_SCORE,
    }  # fmt: skip


def assign_roles(
    features: Sequence[ColumnFeatures], header_prior: Mapping[int, str] | None = None
) -> RoleAssignment:
    n = len(features)
    if n == 0:
        return RoleAssignment((), (), ())
    scores = [role_scores(f, i, n) for i, f in enumerate(features)]
    for col, role in (header_prior or {}).items():
        if 0 <= col < n and role in scores[col]:
            scores[col][role] += HEADER_PRIOR
    slots: list[str] = list(UNIQUE_ROLES) + [r for r in MULTI_ROLES for _ in range(n)]
    matrix = np.array([[scores[c][r] for r in slots] for c in range(n)])
    rows, cols = linear_sum_assignment(matrix, maximize=True)
    roles = ["ignore"] * n
    for r, c in zip(rows, cols, strict=True):
        roles[r] = slots[c]
    margins = []
    for c in range(n):
        own = scores[c][roles[c]]
        other = max(v for k, v in scores[c].items() if k != roles[c])
        margins.append(round(own - other, 3))
    return RoleAssignment(tuple(roles), tuple(scores), tuple(margins))
