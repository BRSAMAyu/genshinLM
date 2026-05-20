from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentic.ui_explorer import UIExplorer
from app_service.agent_controller import AgentController
from app_service.api import create_api_router
from collection.collect_runtime import CollectRuntime
from combat.cooldown_manager import CooldownManager, SkillCooldownConfig
from combat.resource_manager import HPBarTracker
from execution.combat_verifier import CombatVerifier
from execution.mission_node_executor import MissionNodeExecutor
from knowledge.route_selector import RouteSelector
from knowledge.source_resolver import SourceResolver
from learning.failure_clusterer import FailureClusterer
from learning.failure_signature import FailureSignatureBuilder, PrivacyMask
from learning.skill_patch_suggester import SkillPatchSuggester
from open_beta.benchmark_suite import BenchmarkSuite
from open_beta.feedback_package import FeedbackPackageBuilder
from open_beta.skill_workshop import SkillWorkshop
from persistence.hot_resume import HotResume
from persistence.mission_checkpoint import MissionCheckpoint
from planning.intent_parser import IntentParser
from planning.plan_validator import PlanValidator
from planning.task_spec_builder import TaskSpecBuilder


def make_client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    controller = AgentController(root=tmp_path)
    app.include_router(create_api_router(controller))
    return TestClient(app)


def test_knowledge_spatial_routes_and_mission_plan() -> None:
    resolved = SourceResolver().resolve("prepare material x")
    routes = RouteSelector().rank_routes("material_x")
    queue = TaskSpecBuilder().build(IntentParser().parse("准备材料 X，优先打怪，10"))
    validation = PlanValidator().validate(queue, available_skills={"other_skill"})

    assert resolved["ok"] is True
    assert routes["ok"] is True
    assert routes["routes"][0]["waypoint_path"] == ["safe_anchor", "river_crossing", "monster_camp"]
    assert "enter_region_a_v1" in validation["missing_skills"]


def test_skill_binding_verifier_snapshot_and_cleanup() -> None:
    queue = TaskSpecBuilder().build(IntentParser().parse("material x"))
    node = queue.nodes[2]
    executor = MissionNodeExecutor()
    result = executor.execute(
        node,
        [{"skill_id": "safe_combat_playbook_v1", "type": "combat", "environment_profile": "default_1920x1080"}],
        CombatVerifier(),
        {"target_hp_ratio": 0.5},
    )

    assert result.snapshot_id is not None
    assert result.status == "SKIPPED_AFTER_CLEANUP"
    assert result.cleanup_skill_called == "return_to_safe_anchor_v1"


def test_combat_runtime_multimodal_helpers() -> None:
    cooldown = CooldownManager([SkillCooldownConfig("skill_e", 5000)])
    assert cooldown.update_from_ocr("skill_e", "4").remaining_ms == 4000
    assert cooldown.update_from_template("skill_e", is_grey=False).ready is True

    bar = np.zeros((4, 10, 3), dtype=np.uint8)
    bar[:, :5, 0] = 255
    hp = HPBarTracker().estimate_hsv_mask_ratio(bar)
    assert 0.45 <= hp.hp_ratio <= 0.55


def test_collection_runtime_flow() -> None:
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    frame[8:12, 8:12, 1] = 220
    runtime = CollectRuntime()
    approach = runtime.tick(frame)
    success = runtime.tick(frame, ocr_text="Collect", state={"gain_popup": True})

    assert approach.status == "APPROACH"
    assert success.status == "SUCCESS"


def test_agentic_destructive_blacklist_requires_human_override() -> None:
    decisions = UIExplorer().explore_once([{"text": "分解五星武器", "bbox": (1, 1, 10, 10), "confidence": 0.99}])
    assert decisions[0]["gate"]["allow"] is False
    assert decisions[0]["gate"]["level"] == "HUMAN_OVERRIDE_REQUIRED"


def test_failure_learning_privacy_mask_and_patch() -> None:
    image = np.ones((10, 10, 3), dtype=np.uint8) * 255
    masked = PrivacyMask().mask(image, allowed_roi=(2, 2, 4, 4), redacted_rois=[(3, 3, 1, 1)])
    signature = FailureSignatureBuilder().build(
        "combat",
        "safe_combat_v1",
        "TARGET_LOST",
        {"target_confidence_drop": True, "visual_pollution_high": True},
        {"profile_id": "default_1920x1080"},
    )
    clusters = FailureClusterer().cluster([signature])
    patch = SkillPatchSuggester().suggest(signature)

    assert masked[0, 0].sum() == 0
    assert masked[3, 3].sum() == 0
    assert "combat:TARGET_LOST" in clusters
    assert patch["requires_user_confirmation"] is True


def test_hot_resume_and_open_beta_helpers(tmp_path: Path) -> None:
    resume = HotResume(tmp_path)
    checkpoint = MissionCheckpoint("mission_a", "combat", ["enter"], [], "default_1920x1080", "skill_a", "playbook_a")
    resume.save(checkpoint)
    assert resume.can_resume("default_1920x1080")["ok"] is True
    assert resume.can_resume("other_profile")["ok"] is False

    metrics = BenchmarkSuite().summarize([{"final_outcome": "COMPLETE", "skill_success_rate": 1.0, "duration_sec": 3.0}])
    assert metrics["task_completion_rate"] == 1.0
    assert SkillWorkshop().validate_blueprint({"kind": "skill", "id": "s1"}).ok is True
    path = FeedbackPackageBuilder().build(tmp_path / "feedback", "report", {}, [], {})
    assert path.exists()


def test_new_service_endpoints(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.get("/knowledge/resolve", params={"goal": "material x"}).json()["ok"] is True
    assert client.get("/knowledge/routes", params={"resource_id": "material_x"}).json()["routes"]
    mission = client.post("/mission/plan", json={"goal": "prepare material x"}).json()
    assert mission["mission"]["nodes"][0]["verifier"] == "region_entered"
