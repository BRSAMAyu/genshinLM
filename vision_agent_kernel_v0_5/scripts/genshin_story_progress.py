"""Genshin story auto-progression v2 — fast reaction, minimal VLM.

Key changes from v1:
- TEXT_BOX / DIALOG: Space+Click, NO VLM, ~0.4s cycle
- OVERWORLD: try F first (fast), only call VLM when stuck 3+ iterations
- NO double-VLM calls
- VLM auto-fallback to cloud Zhipu if local fails once
- 300 iterations, 0.6s base delay
"""
from __future__ import annotations

import io
import os
import sys
import time
import base64

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_SCRIPT_DIR)
LOG_PATH = os.path.join(_PROJECT_DIR, "_story_progress.log")
MAX_ITERATIONS = 300
LOOP_DELAY = 0.6
WINDOW_TITLE = "原神"

_log = open(LOG_PATH, "w", encoding="utf-8", buffering=1)


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    _log.write(line + "\n")


# ---- Capture ----

_camera = None


def capture_frame():
    global _camera
    import dxcam
    if _camera is None:
        _camera = dxcam.create(output_idx=0, output_color="RGB")
    return _camera.grab()


# ---- Fast detectors (no VLM) ----

def detect_text_box(frame) -> bool:
    """Dialog text box: bright region in bottom 40%."""
    try:
        import numpy as np
        h = frame.shape[0]
        bottom = frame[int(h * 0.6):, :]
        gray = np.mean(bottom, axis=2)
        return float(np.mean(gray > 200)) > 0.12
    except Exception:
        return False


# ---- VLM ----

_vlm_use_cloud = False


def vlm_ask(prompt: str) -> str:
    """Ask VLM — local LM Studio first, cloud Zhipu fallback."""
    global vlm_provider, _vlm_use_cloud
    try:
        frame = capture_frame()
        if frame is None:
            return ""

        # Local LM Studio
        if vlm_provider is not None and not _vlm_use_cloud:
            try:
                from llm.vision_provider import ImageInput
                import cv2
                h, w = frame.shape[:2]
                scale = 1024 / max(h, w)
                if scale < 1.0:
                    small = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                else:
                    small = frame
                _, jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 75])
                image = ImageInput(data=bytes(jpeg), mime_type="image/jpeg")
                result = vlm_provider.describe_image(image, prompt)
                return result.text.strip()
            except Exception as e:
                log(f"  local_vlm_fail: {e}, -> cloud")
                _vlm_use_cloud = True

        # Cloud Zhipu glm-4v-flash
        from PIL import Image
        from core.local_secret_store import LocalSecretStore
        from openai import OpenAI

        img = Image.fromarray(frame)
        ratio = 1024 / max(img.size)
        img = img.resize((int(img.size[0] * ratio), int(img.size[1] * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        b64 = base64.b64encode(buf.getvalue()).decode()

        api_key = LocalSecretStore().get("ZHIPU_API_KEY")
        client = OpenAI(api_key=api_key, base_url="https://open.bigmodel.cn/api/paas/v4")
        resp = client.chat.completions.create(
            model="glm-4v-flash",
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ]}],
            max_tokens=60, temperature=0.1, timeout=5.0,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log(f"  vlm_err: {e}")
        return ""


# ---- Main loop ----

def main() -> None:
    global vlm_provider

    from execution.safe_window_backend import SafeWindowInputBackend
    from perception.genshin_screen_classifier import GenshinScreenClassifier
    from llm.local_vlm_provider import OpenAICompatibleLocalVisionProvider

    backend = SafeWindowInputBackend(
        target_window_title=WINDOW_TITLE,
        pixels_per_degree=8.0,
    )
    classifier = GenshinScreenClassifier()

    # VLM init
    vlm_provider = None
    try:
        local = OpenAICompatibleLocalVisionProvider()
        local_status = local.status()
        if local_status.ok:
            try:
                import json, urllib.request
                with urllib.request.urlopen("http://127.0.0.1:1234/v1/models", timeout=2) as r:
                    models_data = json.loads(r.read().decode())
                model_ids = [m["id"] for m in models_data.get("data", []) if "gemma" in m.get("id", "").lower()]
                detected_model = model_ids[0] if model_ids else local.model
            except Exception:
                detected_model = local.model
            local = OpenAICompatibleLocalVisionProvider(model=detected_model)
            vlm_provider = local
            log(f"VLM: LOCAL ({detected_model}) latency={local_status.latency_ms:.0f}ms")
        else:
            log(f"VLM: cloud Zhipu (local: {local_status.message})")
    except Exception as e:
        log(f"VLM: cloud Zhipu (init error: {e})")

    log("=" * 60)
    log("Genshin Story Progression v2 (fast)")
    log(f"iterations={MAX_ITERATIONS} delay={LOOP_DELAY}s")
    log("=" * 60)

    backend.focus_target_window()
    time.sleep(0.3)

    dialog_count = 0
    last_screen = ""
    same_count = 0

    for i in range(1, MAX_ITERATIONS + 1):
        # Focus check
        if not backend.is_target_focused():
            backend.focus_target_window()
            time.sleep(0.3)
            if not backend.is_target_focused():
                log(f"[{i}] WAIT (no focus)")
                time.sleep(1.0)
                continue

        # Capture + classify
        frame = capture_frame()
        if frame is None:
            time.sleep(LOOP_DELAY)
            continue

        state = classifier.classify(frame)
        screen = state.state
        ind = state.indicators

        if screen == last_screen:
            same_count += 1
        else:
            same_count = 0
            last_screen = screen

        # ---- Helper: ensure focus before input ----
        def ensure_focus() -> bool:
            if backend.is_target_focused():
                return True
            backend.focus_target_window()
            time.sleep(0.3)
            if backend.is_target_focused():
                return True
            log(f"[{i}] focus_lost: {screen}")
            return False

        # === FAST PATHS (no VLM, ~0.3-0.5s) ===

        # 1. Dialog box indicator → Space
        if ind.get("dialog_box"):
            if ensure_focus():
                backend.key_down("space", reason="dialog")
                time.sleep(0.08)
                backend.key_up("space", reason="dialog")
                dialog_count += 1
                log(f"[{i}] DIALOG → Space #{dialog_count}")
                time.sleep(0.3)
            else:
                time.sleep(1.0)
            continue

        # 2. Text box (bright bottom) → Space+Click
        if detect_text_box(frame):
            if ensure_focus():
                backend.key_down("space", reason="text_box")
                time.sleep(0.06)
                backend.key_up("space", reason="text_box")
                backend.left_click(reason="text_click")
                dialog_count += 1
                log(f"[{i}] TEXT_BOX → Space+Click #{dialog_count}")
                time.sleep(0.3)
            else:
                time.sleep(1.0)
            continue

        # 3. Loading → wait
        if ind.get("loading_screen") or screen == "loading":
            log(f"[{i}] LOADING → wait")
            time.sleep(1.5)
            continue

        # 4. Menu → ESC
        if screen == "menu" or screen == "full_menu":
            if ensure_focus():
                backend.key_down("esc", reason="menu")
                time.sleep(0.08)
                backend.key_up("esc", reason="menu")
                log(f"[{i}] MENU → ESC")
                time.sleep(0.6)
            else:
                time.sleep(1.0)
            continue

        # 5. Combat → click
        if ind.get("combat"):
            if ensure_focus():
                backend.left_click(reason="attack")
                log(f"[{i}] COMBAT → click")
                time.sleep(0.3)
            else:
                time.sleep(1.0)
            continue

        # 6. Cutscene (dark) → wait
        if ind.get("dark_frame"):
            log(f"[{i}] CUTSCENE → wait")
            time.sleep(1.5)
            continue

        # === OVERWORLD / UNKNOWN ===
        if ensure_focus():
            backend.key_down("f", reason="try_interact")
            time.sleep(0.08)
            backend.key_up("f", reason="try_interact")
            backend.key_down("space", reason="try_advance")
            time.sleep(0.06)
            backend.key_up("space", reason="try_advance")
            log(f"[{i}] {screen} → F+Space (fast)")
            time.sleep(0.5)
        else:
            time.sleep(1.0)
            continue

        # Only call VLM when stuck for 3+ iterations
        if same_count >= 3 and same_count % 3 == 0:
            desc = vlm_ask(
                "原神。只回答两个字：状态(对话/过场/大世界/战斗/加载) 操作(按F/空格/ESC/等待/走动)"
            )
            log(f"[{i}] STUCK({same_count}) → VLM: {desc[:50]}")
            if ensure_focus():
                dl = desc.lower()
                if "对话" in dl or "空格" in dl:
                    backend.key_down("space", reason="vlm")
                    time.sleep(0.08)
                    backend.key_up("space", reason="vlm")
                    backend.left_click(reason="vlm_click")
                    dialog_count += 1
                elif "走动" in dl:
                    backend.key_down("w", reason="vlm_walk")
                    time.sleep(1.5)
                    backend.key_up("w", reason="vlm_walk")
                elif "esc" in dl:
                    backend.key_down("esc", reason="vlm_esc")
                    time.sleep(0.08)
                    backend.key_up("esc", reason="vlm_esc")
                elif "等待" in dl or "过场" in dl:
                    pass
                else:
                    backend.key_down("f", reason="vlm_default")
                    time.sleep(0.08)
                    backend.key_up("f", reason="vlm_default")
                time.sleep(0.3)

    log("=" * 60)
    log(f"Done. Dialog advances: {dialog_count}")

    global _camera
    if _camera is not None:
        _camera.release()


if __name__ == "__main__":
    main()
