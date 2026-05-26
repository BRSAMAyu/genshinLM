from __future__ import annotations

import json
import logging
from pathlib import Path

from learning.failure_signature import FailureSignature, FailureSignatureBuilder

log = logging.getLogger(__name__)


class TelemetryFailureIngestor:
    def __init__(self) -> None:
        self._builder = FailureSignatureBuilder()

    def ingest_jsonl(self, path: Path) -> list[FailureSignature]:
        failures: list[FailureSignature] = []
        if not path.exists():
            return failures
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                log.warning("Skipping malformed JSON line: %s", line[:120])
                continue
            code = event.get("failure_code") or event.get("failure") or ("TARGET_LOST" if event.get("event") == "target_lost" else None)
            if not code:
                continue
            failures.append(
                self._builder.build(
                    node_type=str(event.get("node_type", event.get("node", "unknown"))),
                    skill_id=str(event.get("skill_id", event.get("skill", "unknown"))),
                    failure_code=str(code),
                    observation=dict(event.get("observation", {})),
                    context=dict(event.get("context", {})),
                )
            )
        return failures
