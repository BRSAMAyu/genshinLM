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
    horizontal_fov_deg: float = 90.0
    obstacle_scenario: str = "simple"
    combat_demo: bool = False


class Pseudo3DScene:
    def __init__(self, config: Pseudo3DSceneConfig | None = None) -> None:
        self._config = config or Pseudo3DSceneConfig()
        self._camera_yaw_deg = 0.0
        self._camera_pitch_deg = 0.0
        self._target_x = 0.0
        self._target_y = 0.0
        self._target_z = 900.0
        angle = random.uniform(0.0, math.tau)
        self._target_vx = math.cos(angle) * 70.0
        self._target_vy = math.sin(angle) * 35.0
        self._target_vz = math.sin(angle) * 45.0
        self._projected_target_size = self._config.target_size
        self._centered_duration = 0.0
        self._target_color_state = "RED"
        self._ignore_first_mouse_motion = True
        self._invisible_until = 0.0
        self._occlusion_until = 0.0
        self._distractor_until = 0.0
        self._chaos_events: list[str] = []
        self._auto_chaos_fired = False
        self._started_at = time.perf_counter()
        self._enemy_warning_until = 0.0
        self._projectile_until = 0.0
        self._danger_zone_until = 0.0
        self._dodge_feedback_until = 0.0
        self._dodge_feedback = "NONE"
        self._hp_ratio = 1.0
        self._dodge_cooldown_until = 0.0
        self._target_stun_until = 0.0
        self._combat_danger_score = 0.0

    def _reset_target(self) -> None:
        self._target_x = 0.0
        self._target_y = 0.0
        self._target_z = 850.0
        self._target_vx = 42.0
        self._target_vy = 18.0
        self._target_vz = 30.0
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
                    self._camera_yaw_deg += dx * 0.12
                    self._camera_pitch_deg += dy * 0.10
                    self._camera_pitch_deg = max(-45.0, min(45.0, self._camera_pitch_deg))

            self._maybe_apply_auto_chaos()
            self._update_combat_state(dt)
            self._update_target(dt)
            target_screen_pos = self._target_screen_position()
            center_error = self._target_center_error(target_screen_pos)
            self._update_trigger_state(dt, center_error)
            screen.fill((0, 0, 0))
            self._draw_static_obstacles(pygame, screen)
            self._draw_combat_danger(pygame, screen)
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
        self._target_z += self._target_vz * dt
        if self._target_x < -520.0 or self._target_x > 520.0:
            self._target_vx *= -1.0
        if self._target_y < -220.0 or self._target_y > 220.0:
            self._target_vy *= -1.0
        if self._target_z < 420.0 or self._target_z > 1500.0:
            self._target_vz *= -1.0

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
        elif key == pygame.K_d:
            self._apply_dodge_feedback()
        elif key == pygame.K_g:
            self._trigger_combat_danger()

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
            self._target_x = 1800.0
            self._target_y = 600.0
            self._target_z = 800.0
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

    def _update_combat_state(self, dt: float) -> None:
        if not self._config.combat_demo:
            return
        now = time.perf_counter()
        cycle = (now - self._started_at) % 5.0
        if cycle < dt:
            self._trigger_combat_danger()
        warning = 1.0 if now < self._enemy_warning_until else 0.0
        projectile = 1.0 if now < self._projectile_until else 0.0
        danger_zone = 1.0 if now < self._danger_zone_until else 0.0
        hp_drop = max(0.0, 1.0 - self._hp_ratio)
        self._combat_danger_score = min(1.0, warning * 0.22 + projectile * 0.28 + danger_zone * 0.24 + hp_drop * 0.18)
        if self._combat_danger_score > 0.65:
            self._hp_ratio = max(0.2, self._hp_ratio - dt * 0.025)
        else:
            self._hp_ratio = min(1.0, self._hp_ratio + dt * 0.012)

    def _trigger_combat_danger(self) -> None:
        now = time.perf_counter()
        self._enemy_warning_until = now + 1.2
        self._projectile_until = now + 1.0
        self._danger_zone_until = now + 1.4
        self._target_stun_until = now + 0.6
        self._record_chaos("COMBAT_DANGER")

    def _apply_dodge_feedback(self) -> None:
        now = time.perf_counter()
        if now < self._dodge_cooldown_until:
            self._dodge_feedback = "DODGE_FAILED_COOLDOWN"
        elif self._combat_danger_score >= 0.45:
            self._dodge_feedback = "DODGE_SUCCESS"
            self._enemy_warning_until = 0.0
            self._projectile_until = 0.0
            self._danger_zone_until = 0.0
            self._dodge_cooldown_until = now + 0.8
        else:
            self._dodge_feedback = "DODGE_NO_THREAT"
            self._dodge_cooldown_until = now + 0.4
        self._dodge_feedback_until = now + 1.2
        self._record_chaos(self._dodge_feedback)

    def _target_screen_position(self) -> tuple[int, int]:
        projected = self._project_world(self._target_x, self._target_y, self._target_z)
        self._projected_target_size = max(18, min(120, int(self._config.target_size * (850.0 / max(self._target_z, 1.0)))))
        return (int(projected[0]), int(projected[1]))

    def _project_world(self, x: float, y: float, z: float) -> tuple[float, float]:
        yaw = math.degrees(math.atan2(x, z)) - self._camera_yaw_deg
        pitch = math.degrees(math.atan2(y, z)) - self._camera_pitch_deg
        half_w = self._config.width / 2.0
        half_h = self._config.height / 2.0
        h_half_fov = math.radians(self._config.horizontal_fov_deg) / 2.0
        v_fov = math.degrees(2.0 * math.atan(math.tan(h_half_fov) * self._config.height / self._config.width))
        v_half_fov = math.radians(v_fov) / 2.0
        screen_x = half_w + math.tan(math.radians(yaw)) / math.tan(h_half_fov) * half_w
        screen_y = half_h + math.tan(math.radians(pitch)) / math.tan(v_half_fov) * half_h
        return (screen_x, screen_y)

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
        size = self._projected_target_size
        screen_x, screen_y = target_screen_pos
        rect = pygame.Rect(screen_x - size // 2, screen_y - size // 2, size, size)
        color = (20, 220, 80) if self._target_color_state == "GREEN" else (220, 20, 20)
        pygame.draw.rect(screen, color, rect)

    def _draw_occluder(self, pygame, screen, target_screen_pos: tuple[int, int]) -> None:
        if time.perf_counter() >= self._occlusion_until:
            return
        size = self._projected_target_size + 38
        screen_x, screen_y = target_screen_pos
        rect = pygame.Rect(screen_x - size // 2, screen_y - size // 2, size, size)
        pygame.draw.rect(screen, (0, 0, 0), rect)

    def _draw_distractor(self, pygame, screen, target_screen_pos: tuple[int, int]) -> None:
        if time.perf_counter() >= self._distractor_until:
            return
        size = self._projected_target_size
        x_offset = -size * 2 if target_screen_pos[0] > self._config.width * 0.55 else size * 2
        y_offset = -int(size * 1.5) if target_screen_pos[1] > self._config.height * 0.55 else int(size * 1.5)
        x = max(size // 2, min(self._config.width - size // 2, int(target_screen_pos[0] + x_offset)))
        y = max(size // 2, min(self._config.height - size // 2, int(target_screen_pos[1] + y_offset)))
        rect = pygame.Rect(x - size // 2, y - size // 2, size, size)
        pygame.draw.rect(screen, (210, 35, 35), rect)

    def _draw_static_obstacles(self, pygame, screen) -> None:
        obstacles = [(-260.0, 0.0, 720.0), (280.0, 30.0, 980.0), (0.0, 90.0, 1300.0)]
        if self._config.obstacle_scenario == "blocked":
            obstacles.append((0.0, 0.0, 540.0))
        elif self._config.obstacle_scenario == "impossible":
            obstacles.extend([(-120.0, 0.0, 500.0), (120.0, 0.0, 500.0), (0.0, 0.0, 450.0)])
        for index, (x, y, z) in enumerate(obstacles):
            sx, sy = self._project_world(x, y, z)
            size = max(32, min(180, int(95.0 * 700.0 / z)))
            color = (70, 90, 130) if index < 3 else (120, 120, 120)
            pygame.draw.rect(screen, color, pygame.Rect(int(sx) - size // 2, int(sy) - size // 2, size, size))

    def _draw_combat_danger(self, pygame, screen) -> None:
        if not self._config.combat_demo:
            return
        now = time.perf_counter()
        if now < self._danger_zone_until:
            radius = int(min(self._config.width, self._config.height) * 0.18)
            surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(surface, (255, 72, 90, 88), (radius, radius), radius)
            screen.blit(surface, (self._config.width // 2 - radius, self._config.height // 2 - radius))
        if now < self._enemy_warning_until:
            pygame.draw.arc(screen, (255, 210, 90), pygame.Rect(450, 140, 380, 260), 0.1, math.pi - 0.1, 6)
        if now < self._projectile_until:
            progress = 1.0 - max(0.0, self._projectile_until - now) / 1.0
            x = int(80 + (self._config.width / 2 - 80) * progress)
            y = int(120 + (self._config.height / 2 - 120) * progress)
            pygame.draw.circle(screen, (255, 120, 40), (x, y), 14)
        if now < self._dodge_feedback_until:
            color = (80, 240, 160) if self._dodge_feedback == "DODGE_SUCCESS" else (255, 120, 120)
            pygame.draw.rect(screen, color, pygame.Rect(self._config.width - 220, 24, 180, 34), 2)

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
            f"camera yaw: {self._camera_yaw_deg:.1f}",
            f"camera pitch: {self._camera_pitch_deg:.1f}",
            f"fov: {self._config.horizontal_fov_deg:.1f}",
            f"target_world_position: ({self._target_x:.1f}, {self._target_y:.1f}, {self._target_z:.1f})",
            f"target_screen_pos: ({screen_x}, {screen_y})",
            f"target_visible: {visible}",
            f"occlusion_state: {'OCCLUDED' if now < self._occlusion_until else 'CLEAR'}",
            f"target_center_error: ({center_error[0]:.1f}, {center_error[1]:.1f})",
            f"centered_duration: {self._centered_duration:.2f}",
            f"target_color_state: {self._target_color_state}",
            f"chaos_active: {','.join(chaos_active) if chaos_active else 'NONE'}",
            f"chaos_events: {','.join(self._chaos_events) if self._chaos_events else 'NONE'}",
            f"danger_score: {self._combat_danger_score:.2f}",
            f"hp: {self._hp_ratio:.2f}",
            f"dodge_cooldown: {max(0.0, self._dodge_cooldown_until - now):.2f}",
            f"dodge_feedback: {self._dodge_feedback if now < self._dodge_feedback_until else 'NONE'}",
            f"target_state: {'STUN' if now < self._target_stun_until else 'RECOVERY'}",
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
    parser.add_argument("--fov", type=float, default=90.0)
    parser.add_argument("--obstacle-scenario", choices=["simple", "blocked", "impossible"], default="simple")
    parser.add_argument("--combat-demo", action="store_true")
    args = parser.parse_args()
    Pseudo3DScene(
        Pseudo3DSceneConfig(
            width=args.width,
            height=args.height,
            debug_overlay=not args.no_debug_overlay,
            title=args.title,
            auto_chaos=args.auto_chaos,
            auto_chaos_delay_sec=args.auto_chaos_delay,
            horizontal_fov_deg=args.fov,
            obstacle_scenario=args.obstacle_scenario,
            combat_demo=args.combat_demo,
        )
    ).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
