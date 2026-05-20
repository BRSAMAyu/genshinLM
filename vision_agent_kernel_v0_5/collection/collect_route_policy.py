from __future__ import annotations

from collection.collectable_detector import CollectableCandidate


class CollectRoutePolicy:
    def choose_next(self, candidates: list[CollectableCandidate]) -> CollectableCandidate | None:
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item.confidence, -item.area))

