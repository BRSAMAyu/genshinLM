from __future__ import annotations

import json
from pathlib import Path


class FeedbackPackageBuilder:
    def build(self, destination: Path, report: str, config_summary: dict, failure_signatures: list[dict], system_info: dict) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        payload = {
            "report": report,
            "config_summary": config_summary,
            "failure_signatures": failure_signatures,
            "system_info": system_info,
            "screenshots": "redacted_or_omitted_by_default",
            "upload_default": False,
        }
        path = destination / "beta_feedback_package.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
