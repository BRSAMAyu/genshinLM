from __future__ import annotations

from collections import defaultdict

from learning.failure_signature import FailureSignature


class FailureClusterer:
    def cluster(self, failures: list[FailureSignature]) -> dict[str, list[FailureSignature]]:
        clusters: dict[str, list[FailureSignature]] = defaultdict(list)
        for failure in failures:
            clusters[f"{failure.node_type}:{failure.failure_code}"].append(failure)
        return dict(clusters)

