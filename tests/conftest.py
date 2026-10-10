"""Shared pytest configuration.

``tests/`` is on ``sys.path`` (rootdir conftest, prepend import mode), so test modules import the
synthetic-token builder as ``from helpers.synth import ...``.
"""

from __future__ import annotations

from hypothesis import HealthCheck, settings

# Deterministic, bounded property runs: no deadline (first calls warm caches), fixed seed.
settings.register_profile(
    "hwsets",
    deadline=None,
    max_examples=100,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("hwsets")
