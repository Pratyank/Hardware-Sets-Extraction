"""Export the JSON Schema of the output models (``make schema``)."""

from __future__ import annotations

import json
from pathlib import Path

from hwsets.models import DocumentResult, FlatDocument


def write_schema(path: Path = Path("schema.json")) -> None:
    schema = {
        "DocumentResult": DocumentResult.model_json_schema(),
        "FlatDocument": FlatDocument.model_json_schema(),
    }
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_schema()
