from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True, slots=True)
class FrameMeta:
    frame_id: int
    timestamp: float
    region: str
    rel_path: str
    hash_hex: str


def _numpy_perceptual_hash(image: np.ndarray, hash_size: int = 8) -> str:
    gray = np.dot(image[..., :3].astype(np.float64), [0.2989, 0.5870, 0.1140])
    small = gray[
        np.linspace(0, gray.shape[0] - 1, hash_size, dtype=int)[:, None],
        np.linspace(0, gray.shape[1] - 1, hash_size, dtype=int)[None, :],
    ]
    median = np.median(small)
    bits = (small > median).flatten()
    return "".join("1" if b else "0" for b in bits)


def _compute_hash(image: np.ndarray, hash_size: int = 8) -> str:
    try:
        import imagehash  # type: ignore[import-not-found]
        from PIL import Image

        pil_img = Image.fromarray(image)
        h = imagehash.phash(pil_img, hash_size=hash_size)
        return str(h)
    except ImportError:
        return _numpy_perceptual_hash(image, hash_size)


def _hamming_distance(h1: str, h2: str) -> int:
    if len(h1) != len(h2):
        return len(h1) + len(h2)
    return sum(c1 != c2 for c1, c2 in zip(h1, h2))


def _hex_hamming_distance(h1: str, h2: str) -> int:
    if len(h1) != len(h2):
        return max(len(h1), len(h2)) * 4
    v1 = int(h1, 16)
    v2 = int(h2, 16)
    return bin(v1 ^ v2).count("1")


def _is_duplicate(hash_hex: str, recent_hashes: list[str], threshold: int) -> bool:
    for rh in recent_hashes:
        try:
            dist = _hex_hamming_distance(hash_hex, rh)
        except ValueError:
            dist = _hamming_distance(hash_hex, rh)
        if dist < threshold:
            return True
    return False


def _capture_frame(
    window_title: str,
) -> np.ndarray | None:
    try:
        import ctypes
        import ctypes.wintypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]

        hwnd = user32.FindWindowW(None, window_title)
        if not hwnd:
            print(f"[collect] window '{window_title}' not found", flush=True)
            return None

        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        region = (rect.left, rect.top, rect.right, rect.bottom)

        import dxcam  # type: ignore[import-not-found]

        camera = dxcam.create(output_color="RGB")
        camera.start(region=region, target_fps=1)
        time.sleep(0.1)
        frame = camera.get_latest_frame()
        camera.stop()
        del camera
        return frame
    except Exception as exc:
        print(f"[collect] capture error: {exc}", flush=True)
        return None


def _capture_frame_mss(window_title: str) -> np.ndarray | None:
    try:
        import ctypes
        import ctypes.wintypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]

        hwnd = user32.FindWindowW(None, window_title)
        if not hwnd:
            print(f"[collect] window '{window_title}' not found", flush=True)
            return None

        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))

        import mss  # type: ignore[import-not-found]

        monitor = {
            "left": rect.left,
            "top": rect.top,
            "width": rect.right - rect.left,
            "height": rect.bottom - rect.top,
        }
        with mss.mss() as sct:
            shot = sct.grab(monitor)
            return np.asarray(shot, dtype=np.uint8)[..., :3]
    except Exception as exc:
        print(f"[collect] mss capture error: {exc}", flush=True)
        return None


def _setup_directories(output_dir: Path) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    raw_dir = output_dir
    images_dir = raw_dir / "images"
    train_img_dir = images_dir / "train"
    val_img_dir = images_dir / "val"
    labels_dir = raw_dir / "labels"
    train_lbl_dir = labels_dir / "train"
    val_lbl_dir = labels_dir / "val"
    for d in (train_img_dir, val_img_dir, train_lbl_dir, val_lbl_dir):
        d.mkdir(parents=True, exist_ok=True)
    return raw_dir, train_img_dir, val_img_dir, train_lbl_dir, val_lbl_dir


def _write_dataset_yaml(dataset_dir: Path) -> None:
    content = (
        f"path: {dataset_dir.resolve()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "\n"
        "nc: 10\n"
        "names:\n"
        "  0: monster_normal\n"
        "  1: monster_elite\n"
        "  2: monster_boss\n"
        "  3: ore\n"
        "  4: plant\n"
        "  5: chest\n"
        "  6: loot_beam\n"
        "  7: interaction_prompt\n"
        "  8: hp_bar_enemy\n"
        "  9: danger_zone\n"
    )
    (dataset_dir / "dataset.yaml").write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect training data from Genshin Impact for YOLO model training."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="datasets/genshin_raw/",
        help="Output directory for raw frames (default: datasets/genshin_raw/)",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=1.0,
        help="Capture rate in FPS (default: 1)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=0,
        help="Maximum frames to capture, 0=unlimited (default: 0)",
    )
    parser.add_argument(
        "--region",
        type=str,
        default="unknown",
        help="Region label for metadata tagging (default: unknown)",
    )
    parser.add_argument(
        "--window-title",
        type=str,
        default="原神",
        help="Target window title (default: 原神)",
    )
    parser.add_argument(
        "--hash-threshold",
        type=int,
        default=8,
        help="Perceptual hash difference threshold for dedup (default: 8)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    fps = args.fps
    max_frames = args.max_frames
    region_label = args.region
    window_title = args.window_title
    hash_threshold = args.hash_threshold
    interval = 1.0 / fps if fps > 0 else 1.0

    raw_dir, train_img_dir, val_img_dir, train_lbl_dir, val_lbl_dir = _setup_directories(output_dir)
    meta_path = raw_dir / "metadata.jsonl"

    recent_hashes: list[str] = []
    max_recent = 50
    frame_count = 0
    dedup_count = 0
    saved_count = 0
    start_time = time.perf_counter()

    print(
        f"[collect] output_dir={output_dir} fps={fps} region={region_label} "
        f"window={window_title} hash_threshold={hash_threshold}",
        flush=True,
    )
    print(f"[collect] press Ctrl+C to stop", flush=True)

    meta_file = meta_path.open("a", encoding="utf-8")

    try:
        while True:
            if max_frames > 0 and frame_count >= max_frames:
                print(f"[collect] reached max_frames={max_frames}", flush=True)
                break

            loop_start = time.perf_counter()

            frame = _capture_frame(window_title)
            if frame is None:
                frame = _capture_frame_mss(window_title)
            if frame is None:
                print("[collect] no frame captured, retrying...", flush=True)
                time.sleep(interval)
                frame_count += 1
                continue

            hash_hex = _compute_hash(frame)
            frame_count += 1

            if _is_duplicate(hash_hex, recent_hashes, hash_threshold):
                dedup_count += 1
                elapsed = time.perf_counter() - start_time
                print(
                    f"[collect] frame={frame_count} dedup={dedup_count} "
                    f"saved={saved_count} elapsed={elapsed:.1f}s "
                    f"fps={frame_count / max(elapsed, 0.001):.1f}",
                    flush=True,
                )
                time.sleep(max(0, interval - (time.perf_counter() - loop_start)))
                continue

            recent_hashes.append(hash_hex)
            if len(recent_hashes) > max_recent:
                recent_hashes = recent_hashes[-max_recent:]

            ts = time.perf_counter()
            filename = f"frame_{frame_count:06d}_{ts:.3f}.png"
            rel_path = f"images/train/{filename}"

            from PIL import Image

            pil_image = Image.fromarray(frame)
            pil_image.save(train_img_dir / filename)

            lbl_filename = filename.replace(".png", ".txt")
            (train_lbl_dir / lbl_filename).write_text("", encoding="utf-8")

            saved_count += 1

            meta = FrameMeta(
                frame_id=frame_count,
                timestamp=ts,
                region=region_label,
                rel_path=rel_path,
                hash_hex=hash_hex,
            )
            meta_file.write(json.dumps(meta.__dict__, ensure_ascii=False) + "\n")
            meta_file.flush()

            elapsed = time.perf_counter() - start_time
            print(
                f"[collect] frame={frame_count} dedup={dedup_count} "
                f"saved={saved_count} elapsed={elapsed:.1f}s "
                f"fps={frame_count / max(elapsed, 0.001):.1f} "
                f"hash={hash_hex}",
                flush=True,
            )

            sleep_time = interval - (time.perf_counter() - loop_start)
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n[collect] interrupted by user", flush=True)
    finally:
        meta_file.close()

    _write_dataset_yaml(raw_dir)

    elapsed = time.perf_counter() - start_time
    print(
        f"[collect] done: frames={frame_count} saved={saved_count} "
        f"duplicates={dedup_count} elapsed={elapsed:.1f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
