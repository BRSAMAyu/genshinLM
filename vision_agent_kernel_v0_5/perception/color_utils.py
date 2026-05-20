from __future__ import annotations

import numpy as np

try:
    import cv2  # type: ignore[import-not-found]

    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False


def bgr_to_hsv_cv(frame: np.ndarray) -> np.ndarray:
    """Convert a BGR uint8 frame to HSV in OpenCV scale (H:0-180, S:0-255, V:0-255).

    Uses cv2.cvtColor when available; falls back to a pure-numpy implementation
    that produces the same scale.
    """
    if _HAS_CV2:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # Pure-numpy fallback — produce H:0-180, S:0-255, V:0-255
    bgr = frame.astype(np.float32) / 255.0
    b, g, r = bgr[:, :, 0], bgr[:, :, 1], bgr[:, :, 2]
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    delta = maxc - minc

    hue = np.zeros_like(maxc)
    nonzero = delta > 1e-6
    safe_delta = np.where(nonzero, delta, 1.0)
    hue = np.where((maxc == r) & nonzero, ((g - b) / safe_delta) % 6.0, hue)
    hue = np.where((maxc == g) & nonzero, ((b - r) / safe_delta) + 2.0, hue)
    hue = np.where((maxc == b) & nonzero, ((r - g) / safe_delta) + 4.0, hue)

    # OpenCV H is 0-180 (half of 0-360 degrees)
    h_cv = (hue * 30.0).astype(np.uint8)  # hue*60/2 -> 0..180
    s_cv = np.divide(delta, maxc, out=np.zeros_like(delta), where=maxc > 1e-6)
    s_cv = (s_cv * 255.0).astype(np.uint8)
    v_cv = (maxc * 255.0).astype(np.uint8)

    return np.stack([h_cv, s_cv, v_cv], axis=-1)


def hsv_in_range(
    hsv_frame: np.ndarray,
    h_lo: int,
    h_hi: int,
    s_lo: int,
    v_lo: int,
) -> np.ndarray:
    """Return a boolean mask where pixels are within the given HSV bounds.

    Parameters use OpenCV HSV scale: H 0-180, S 0-255, V 0-255.
    ``h_lo`` and ``h_hi`` define an inclusive H range (wraps around 180 if
    h_lo > h_hi).  Only lower bounds are exposed for S and V; upper bounds
    default to 255.
    """
    h: np.ndarray = hsv_frame[:, :, 0]
    s: np.ndarray = hsv_frame[:, :, 1]
    v: np.ndarray = hsv_frame[:, :, 2]

    s_mask = s >= s_lo
    v_mask = v >= v_lo

    if h_lo <= h_hi:
        h_mask = (h >= h_lo) & (h <= h_hi)
    else:
        # Wrap-around (e.g. red: h_lo=160, h_hi=10)
        h_mask = (h >= h_lo) | (h <= h_hi)

    return h_mask & s_mask & v_mask
