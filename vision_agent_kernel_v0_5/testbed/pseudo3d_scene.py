from __future__ import annotations

import argparse
import math
import random
import time
from dataclasses import dataclass


@dataclass(slots=True)
class Pseudo3DSceneConfig:
    width: int = 1280
    height: int = 720
    target_size: int = 64
    fps: int = 60
    debug_overlay: bool = True
    centered_threshold_px: float = 1000.0
    green_hold_seconds: float = 1.0
    title: str = "vision_agent_kernel_v0_5 pseudo3d_scene"
    auto_chaos: str | None = None
    auto_chaos_delay_sec: float = 1.0


class Pseudo3DScene:
    def __init__(self, config: Pseudo3DSceneConfig | None = None) -> None:
        self._config = config or Pseudo3DSceneConfig()
        self._camera_x = 0.0
        self._camera_y = 0.0
        self._target_x = self._config.width / 2.0
        self._target_y = self._config.height / 2.0
        angle = random.uniform(0.0, math.tau)
        self._target_vx = math.cos(angle) * 70.0
        self._target_vy = math.sin(angle) * 50.0
        self._centered_duration = 0.0
        self._target_color_state = "RED"
        self._ignore_first_mouse_motion = True
        self._invisible_until = 0.0
        self._occlusion_until = 0.0
        self._distractor_until = 0.0
        self._chaos_events: list[str] = []
        self._auto_chaos_fired = False
        self._started_at = time.perf_counter()

    def _reset_target(self) -> None:
        self._target_x = self._camera_x + self._config.width / 2.0
        self._target_y = self._camera_y + self._config.height / 2.0
        self._target_vx = 42.0
        self._target_vy = 28.0
        self._centered_duration = 0.0
        self._target_color_state = "RED"

    def run(self) -> None:
        try:
            import pygame
        except ImportError as exc:
            raise RuntimeError("pygame is required for the pseudo3d testbed") from exc

        pygame.init()
        screen = pygame.display.set_mode((self._config.width, self._config.height))
        pygame.display.set_caption(self._config.title)
        font = pygame.font.SysFont("consolas", 18)
        clock = pygame.time.Clock()
        pygame.mouse.set_visible(True)
        pygame.event.set_grab(False)
        running = True

        while running:
            dt = clock.tick(self._config.fps) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    self._handle_keydown(pygame, event.key)
                elif event.type == pygame.MOUSEMOTION:
                    dx, dy = event.rel
                    if self._ignore_first_mouse_motion:
                        self._ignore_first_mouse_motion = False
                        continue
                    if abs(dx) > 160 or abs(dy) > 160:
                        continue
                    # The viewport follows mouse motion, so world objects appear to move
                    # in the opposite direction on screen: screen = world - camera.
                    self._camera_x += dx
                    self._camera_y += dy

            self._maybe_apply_auto_chaos()
            self._update_target(dt)
            target_screen_pos = self._target_screen_position()
            center_error = self._target_center_error(target_screen_pos)
            self._update_trigger_state(dt, center_error)
            screen.fill((0, 0, 0))
            self._draw_distractor(pygame, screen, target_screen_pos)
            self._draw_target(pygame, screen, target_screen_pos)
            self._draw_occluder(pygame, screen, target_screen_pos)
            if self._config.debug_overlay:
                self._draw_debug_overlay(pygame, screen, font, target_screen_pos, center_error)
            pygame.display.flip()

        pygame.quit()

    def _update_target(self, dt: float) -> None:
        self._target_x += self._target_vx * dt
        self._target_y += self._target_vy * dt
        margin = 240.0
        if self._target_x < -margin or self._target_x > self._config.width + margin:
            self._target_vx *= -1.0
        if self._target_y < -margin or self._target_y > self._config.height + margin:
            self._target_vy *= -1.0

    def _handle_keydown(self, pygame, key: int) -> None:
        if key == pygame.K_SPACE:
            self._apply_chaos("disappear")
        elif key == pygame.K_t:
            self._apply_chaos("teleport")
        elif key == pygame.K_o:
            self._apply_chaos("occlusion")
        elif key == pygame.K_m:
            self._apply_chaos("distractor")
        elif key == pygame.K_r:
            self._reset_target()
            self._record_chaos("RESET_TARGET")

    def _maybe_apply_auto_chaos(self) -> None:
        if self._auto_chaos_fired or self._config.auto_chaos is None:
            return
        if time.perf_counter() - self._started_at < self._config.auto_chaos_delay_sec:
            return
        self._auto_chaos_fired = True
        self._apply_chaos(self._config.auto_chaos)

    def _apply_chaos(self, scenario: str) -> None:
        now = time.perf_counter()
        if scenario == "disappear":
            self._invisible_until = now + 3.0
            self._record_chaos("DISAPPEAR_3S")
        elif scenario == "teleport":
            self._target_x = self._config.width + 900.0
            self._target_y = self._config.height + 600.0
            self._record_chaos("TELEPORT_OFFSCREEN")
        elif scenario == "occlusion":
            self._reset_target()
            self._occlusion_until = now + 2.0
            self._record_chaos("OCCLUSION_2S")
        elif scenario == "distractor":
            self._reset_target()
            self._distractor_until = now + 4.0
            self._record_chaos("DISTRACTOR_4S")

    def _record_chaos(self, name: str) -> None:
        self._chaos_events.append(name)
        self._chaos_events = self._chaos_events[-4:]
        print(f"[Pseudo3DScene] chaos_event={name}", flush=True)

    def _target_screen_position(self) -> tuple[int, int]:
        return (int(self._target_x - self._camera_x), int(self._target_y - self._camera_y))

    def _target_center_error(self, target_screen_pos: tuple[int, int]) -> tuple[float, float]:
        screen_x, screen_y = target_screen_pos
        return (screen_x - self._config.width / 2.0, screen_y - self._config.height / 2.0)

    def _update_trigger_state(self, dt: float, center_error: tuple[float, float]) -> None:
        distance = math.hypot(center_error[0], center_error[1])
        if distance <= self._config.centered_threshold_px:
            self._centered_duration += dt
        else:
            self._centered_duration = max(0.0, self._centered_duration - dt * 0.25)
        self._target_color_state = (
            "GREEN"
            if self._centered_duration >= self._config.green_hold_seconds
            else "RED"
        )

    def _draw_target(self, pygame, screen, target_screen_pos: tuple[int, int]) -> None:
        if time.perf_counter() < self._invisible_until:
            return
        size = self._config.target_size
        screen_x, screen_y = target_screen_pos
        rect = pygame.Rect(screen_x - size // 2, screen_y - size // 2, size, size)
        color = (20, 220, 80) if self._target_color_state == "GREEN" else (220, 20, 20)
        pygame.draw.rect(screen, color, rect)

    def _draw_occluder(self, pygame, screen, target_screen_pos: tuple[int, int]) -> None:
        if time.perf_counter() >= self._occlusion_until:
            return
        size = self._config.target_size + 28
        screen_x, screen_y = target_screen_pos
        rect = pygame.Rect(screen_x - size // 2, screen_y - size // 2, size, size)
        pygame.draw.rect(screen, (0, 0, 0), rect)

    def _draw_distractor(self, pygame, screen, target_screen_pos: tuple[int, int]) -> None:
        if time.perf_counter() >= self._distractor_until:
            return
        size = self._config.target_size
        x_offset = -size * 2 if target_screen_pos[0] > self._config.width * 0.55 else size * 2
        y_offset = -int(size * 1.5) if target_screen_pos[1] > self._config.height * 0.55 else int(size * 1.5)
        x = max(size // 2, min(self._config.width - size // 2, int(target_screen_pos[0] + x_offset)))
        y = max(size // 2, min(self._config.height - size // 2, int(target_screen_pos[1] + y_offset)))
        rect = pygame.Rect(x - size // 2, y - size // 2, size, size)
        pygame.draw.rect(screen, (210, 35, 35), rect)

    def _draw_debug_overlay(
        self,
        pygame,
        screen,
        font,
        target_screen_pos: tuple[int, int],
        center_error: tuple[float, float],
    ) -> None:
        screen_x, screen_y = target_screen_pos
        visible = (
            -self._config.target_size <= screen_x <= self._config.width + self._config.target_size
            and -self._config.target_size <= screen_y <= self._config.height + self._config.target_size
            and time.perf_counter() >= self._invisible_until
        )
        chaos_active = []
        now = time.perf_counter()
        if now < self._invisible_until:
            chaos_active.append("INVISIBLE")
        if now < self._occlusion_until:
            chaos_active.append("OCCLUDED")
        if now < self._distractor_until:
            chaos_active.append("DISTRACTOR")
        lines = [
            f"yaw: {self._camera_x:.1f}",
            f"pitch: {self._camera_y:.1f}",
            f"target_screen_pos: ({screen_x}, {screen_y})",
            f"target_visible: {visible}",
            f"target_center_error: ({center_error[0]:.1f}, {center_error[1]:.1f})",
            f"centered_duration: {self._centered_duration:.2f}",
            f"target_color_state: {self._target_color_state}",
            f"chaos_active: {','.join(chaos_active) if chaos_active else 'NONE'}",
            f"chaos_events: {','.join(self._chaos_events) if self._chaos_events else 'NONE'}",
        ]
        for index, line in enumerate(lines):
            surface = font.render(line, True, (240, 240, 240))
            screen.blit(surface, (12, 12 + index * 22))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a black-background moving red-block testbed.")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--no-debug-overlay", action="store_true")
    parser.add_argument("--title", default="vision_agent_kernel_v0_5 pseudo3d_scene")
    parser.add_argument("--auto-chaos", choices=["disappear", "teleport", "occlusion", "distractor"])
    parser.add_argument("--auto-chaos-delay", type=float, default=1.0)
    args = parser.parse_args()
    Pseudo3DScene(
        Pseudo3DSceneConfig(
            width=args.width,
            height=args.height,
            debug_overlay=not args.no_debug_overlay,
            title=args.title,
            auto_chaos=args.auto_chaos,
            auto_chaos_delay_sec=args.auto_chaos_delay,
        )
    ).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
