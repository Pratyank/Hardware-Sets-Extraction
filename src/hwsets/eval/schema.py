"""Pydantic result models for evaluation (all JSON-serializable)."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydField

FIELDS: Final[tuple[str, ...]] = (
    "qty",
    "qty_unit",
    "description",
    "catalog_number",
    "mfr",
    "finish",
    "notes",
)
# Fields that carry a ``Field.confidence`` in the predicted ``Component``.
CONFIDENCE_FIELDS: Final[tuple[str, ...]] = (
    "qty",
    "description",
    "catalog_number",
    "mfr",
    "finish",
    "notes",
)
FUZZY_FIELDS: Final[tuple[str, ...]] = ("description", "catalog_number")
GOLD_ROLES: Final[tuple[str, ...]] = ("mfr", "finish")
PRED_ROLES: Final[tuple[str, ...]] = ("mfr", "finish", "other", "missing")
# [lo, hi) except the last bucket, which is closed: [0.9, 1.0].
BUCKETS: Final[tuple[tuple[float, float], ...]] = (
    (0.0, 0.2),
    (0.2, 0.4),
    (0.4, 0.6),
    (0.6, 0.8),
    (0.8, 0.9),
    (0.9, 1.0),
)

MatchMethod = Literal["number", "iou"]
ErrorKind = Literal[
    "missed_set",
    "spurious_set",
    "wrong_status",
    "wrong_mfr",
    "wrong_finish",
    "wrong_qty",
    "wrong_field",
    "missed_component",
    "spurious_component",
]
SEVERITY: Final[dict[str, int]] = {
    "missed_set": 4,
    "wrong_mfr": 3,
    "wrong_finish": 3,
    "wrong_qty": 2,
    "wrong_status": 1,
    "wrong_field": 1,
    "missed_component": 1,
    "spurious_component": 1,
    "spurious_set": 1,
}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


def ratio(num: float, den: float, empty: float = 1.0) -> float:
    """``num / den``; a vacuous ratio (``den == 0``) is ``empty`` (default 1.0)."""
    return num / den if den else empty


def f1(p: float, r: float) -> float:
    return 2 * p * r / (p + r) if p + r else 0.0


class Count(_Model):
    correct: int = 0
    total: int = 0

    @property
    def accuracy(self) -> float:
        return ratio(self.correct, self.total)

    def add(self, other: Count) -> Count:
        return Count(correct=self.correct + other.correct, total=self.total + other.total)


class Mean(_Model):
    """A running mean kept as sum + count so documents aggregate exactly."""

    sum: float = 0.0
    count: int = 0

    @property
    def mean(self) -> float:
        return ratio(self.sum, self.count)

    def add(self, other: Mean) -> Mean:
        return Mean(sum=self.sum + other.sum, count=self.count + other.count)


class ReliabilityBucket(_Model):
    lo: float
    hi: float
    count: int = 0
    correct: int = 0
    accuracy: float | None = None  # None when the bucket is empty


class FieldDiff(_Model):
    field: str
    gold: str | int | None
    pred: str | int | None
    confidence: float | None = None


class ComponentEval(_Model):
    gold_idx: int | None  # index in the gold set's components (None: spurious)
    pred_idx: int | None  # index in the predicted set's components (None: missed)
    similarity: float | None = None  # token_set_ratio of description + catalog, 0..100
    field_correct: dict[str, bool] = PydField(default_factory=dict)
    diffs: list[FieldDiff] = PydField(default_factory=list)


class SetEval(_Model):
    set_number: str  # gold number if any, else predicted
    gold_idx: int | None  # index into gold.sets (None: spurious)
    pred_idx: int | None  # index into pred.sets (None: missed)
    method: MatchMethod | None = None
    page: int | None = None  # first page (gold if matched/missed, else predicted)
    line_id: str | None = None  # first line id if known
    gold_status: str | None = None
    pred_status: str | None = None
    status_correct: bool | None = None
    location_iou: float | None = None
    components: list[ComponentEval] = PydField(default_factory=list)
    n_missed_components: int = 0
    n_spurious_components: int = 0
    fully_correct: bool = False


class ErrorItem(_Model):
    doc_id: str
    kind: ErrorKind
    severity: int
    set_number: str
    set_idx: int | None  # predicted set index (UI link target); None for missed sets
    page: int | None
    line_id: str | None = None
    field: str | None = None
    gold: str | int | None = None
    pred: str | int | None = None
    message: str = ""


class Totals(_Model):
    """Additive counts shared by DocEval and EvalSummary."""

    n_gold_sets: int = 0
    n_pred_sets: int = 0
    n_matched_sets: int = 0
    n_matched_by_iou: int = 0
    status: Count = PydField(default_factory=Count)
    n_gold_components: int = 0  # components of matched gold sets
    n_pred_components: int = 0  # components of matched predicted sets
    n_matched_components: int = 0
    fields: dict[str, Count] = PydField(default_factory=dict)
    fuzzy: dict[str, Mean] = PydField(default_factory=dict)
    confusion: dict[str, dict[str, int]] = PydField(default_factory=dict)
    location: Mean = PydField(default_factory=Mean)
    n_fully_correct: int = 0
    reliability: list[ReliabilityBucket] = PydField(default_factory=list)

    # -- derived ------------------------------------------------------------------
    @property
    def set_recall(self) -> float:
        return ratio(self.n_matched_sets, self.n_gold_sets)

    @property
    def set_precision(self) -> float:
        return ratio(self.n_matched_sets, self.n_pred_sets)

    @property
    def component_recall(self) -> float:
        return ratio(self.n_matched_components, self.n_gold_components)

    @property
    def component_precision(self) -> float:
        return ratio(self.n_matched_components, self.n_pred_components)

    @property
    def set_fully_correct(self) -> float:
        return ratio(self.n_fully_correct, self.n_gold_sets)


class Metrics(_Model):
    """Headline rates derived from :class:`Totals` (stored so report.json is self-contained)."""

    set_recall: float
    set_precision: float
    set_f1: float
    status_accuracy: float
    component_recall: float
    component_precision: float
    component_f1: float
    field_accuracy: dict[str, float]
    fuzzy: dict[str, float]
    location_iou: float
    set_fully_correct: float

    @classmethod
    def from_totals(cls, t: Totals) -> Metrics:
        return cls(
            set_recall=t.set_recall,
            set_precision=t.set_precision,
            set_f1=f1(t.set_precision, t.set_recall),
            status_accuracy=t.status.accuracy,
            component_recall=t.component_recall,
            component_precision=t.component_precision,
            component_f1=f1(t.component_precision, t.component_recall),
            field_accuracy={k: v.accuracy for k, v in t.fields.items()},
            fuzzy={k: v.mean for k, v in t.fuzzy.items()},
            location_iou=t.location.mean,
            set_fully_correct=t.set_fully_correct,
        )


class DocEval(_Model):
    doc_id: str
    source_pdf: str
    gold_pages: str | None = None
    totals: Totals
    metrics: Metrics
    sets: list[SetEval] = PydField(default_factory=list)
    errors: list[ErrorItem] = PydField(default_factory=list)


class EvalSummary(_Model):
    n_docs: int
    totals: Totals
    metrics: Metrics  # micro-averaged over all documents
    macro: dict[str, float] = PydField(default_factory=dict)  # mean of per-doc headline rates
