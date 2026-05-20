from __future__ import annotations

import numpy as np

from perception.viewport import ViewportConfig, ViewportTransformer


def test_viewport_normalizes_to_1280x720() -> None:
    viewport = ViewportTransformer()
    image = np.zeros((360, 640, 3), dtype=np.uint8)

    normalized = viewport.normalize(image)

    assert normalized.shape == (720, 1280, 3)
    assert normalized.flags["C_CONTIGUOUS"]


def test_viewport_coordinate_mapping_round_trip() -> None:
    viewport = ViewportTransformer(ViewportConfig(width=1280, height=720))
    source_size = (1920, 1080)
    source_point = (960.0, 540.0)

    viewport_point = viewport.source_to_viewport(source_point, source_size)
    restored = viewport.viewport_to_source(viewport_point, source_size)

    assert viewport_point == (640.0, 360.0)
    assert restored == source_point
