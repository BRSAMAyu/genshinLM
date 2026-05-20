from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.timebase import Timebase
from perception.capture_base import CaptureConfig
from perception.dxcam_capture import DxcamCapturer
from perception.ultralytics_tracker import UltralyticsTracker, UltralyticsTrackerConfig
from perception.visual_trigger_detector import ColorTargetTracker, VisualTriggerDetector


def _video_frames(path: str):
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("opencv-python is required for --video input") from exc
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise RuntimeError(f"could not open video: {path}")
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            yield cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    finally:
        capture.release()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Ultralytics YOLO track-mode smoke test.")
    parser.add_argument("--model-path", default="")
    parser.add_argument("--tracker", default="botsort.yaml")
    parser.add_argument("--video")
    parser.add_argument("--screen", action="store_true")
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--conf-threshold", type=float, default=0.35)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--fallback-lightweight", action="store_true")
    args = parser.parse_args()

    if not args.video and not args.screen:
        parser.error("choose --video PATH or --screen")

    timebase = Timebase()
    if args.model_path:
        tracker = UltralyticsTracker(
            UltralyticsTrackerConfig(
                model_path=args.model_path,
                tracker=args.tracker,
                conf_threshold=args.conf_threshold,
                iou_threshold=args.iou_threshold,
                device=args.device,
            ),
            timebase=timebase,
        )
        lightweight = None
    elif args.fallback_lightweight:
        tracker = None
        lightweight = (VisualTriggerDetector(), ColorTargetTracker())
    else:
        print(
            "[yolo_tracking_test] missing --model-path. Use --fallback-lightweight for testbed red-target fallback.",
            flush=True,
        )
        return 2

    capturer = None
    frames = None
    if args.video:
        frames = _video_frames(args.video)
    else:
        capturer = DxcamCapturer(CaptureConfig(target_fps=30.0, output_color="RGB"), timebase=timebase)
        capturer.start()

    started = timebase.now()
    frame_id = 0
    try:
        while timebase.now() - started < args.seconds:
            if frames is not None:
                try:
                    frame = next(frames)
                except StopIteration:
                    break
                timestamp = timebase.now()
            else:
                assert capturer is not None
                packet = capturer.get_latest_frame()
                if packet is None:
                    time.sleep(0.01)
                    continue
                frame = packet.image
                timestamp = packet.timestamp
                frame_id = packet.frame_id
            if frames is not None:
                frame_id += 1
            if tracker is not None:
                track = tracker.update(frame, frame_id=frame_id, timestamp=timestamp)
            else:
                detector, red_tracker = lightweight
                detection = detector.detect_target(frame, frame_id, timestamp)
                track = red_tracker.update(detection, frame_id, timestamp)
            print(
                "[yolo_track_panel] "
                f"frame_id={frame_id} "
                f"tracker={args.tracker if tracker is not None else 'lightweight'} "
                f"track_id={track.track_id if track else None} "
                f"state={track.state if track else 'NONE'} "
                f"class={track.class_id if track else None} "
                f"center={track.smoothed_center_px if track else None} "
                f"confidence={track.confidence if track else None}",
                flush=True,
            )
            time.sleep(0.01)
    finally:
        if capturer is not None:
            capturer.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
