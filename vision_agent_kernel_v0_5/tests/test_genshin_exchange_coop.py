from __future__ import annotations

import json
import hashlib
from pathlib import Path

import numpy as np
import pytest
import yaml

from app_service.skill_exchange import SkillExchange, SkillManifest, ExportBundle
from perception.coop_filter import CoOpFilter, CoOpDetection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_skills_dir(tmp_path: Path) -> Path:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_data = {
        "skills": {
            "test_pyro_combo": {
                "skill_id": "test_pyro_combo",
                "name": "Test Pyro Combo",
                "type": "combat",
                "environment_profile": "genshin_1920x1080",
                "version": "1.0.0",
                "author": "tester",
                "description": "A test pyro combo skill",
                "created_at": "2025-01-01",
                "game_version": "5.0",
                "tags": ["combat", "pyro"],
                "steps": [
                    {"step_id": "s1", "type": "action_sequence", "label": "Attack"},
                ],
                "visual_triggers": {},
                "success_criteria": [],
                "failure_policy": {},
                "safety": {},
            }
        }
    }
    (skills_dir / "genshin_test_skills.yaml").write_text(
        yaml.dump(skill_data, allow_unicode=True), encoding="utf-8"
    )
    return skills_dir


@pytest.fixture()
def exchange(tmp_path: Path) -> SkillExchange:
    return SkillExchange(exchange_dir=tmp_path / "exchange")


# ---------------------------------------------------------------------------
# SkillExchange Tests
# ---------------------------------------------------------------------------


class TestSkillManifest:
    def test_skill_manifest_fields(self) -> None:
        m = SkillManifest(
            skill_id="s1",
            name="Skill 1",
            version="1.0",
            author="a",
            description="d",
            created_at="2025-01-01",
            game_version="5.0",
            tags=["t"],
            content_hash="abc",
        )
        assert m.skill_id == "s1"
        assert m.name == "Skill 1"
        assert m.version == "1.0"
        assert m.author == "a"
        assert m.description == "d"
        assert m.created_at == "2025-01-01"
        assert m.game_version == "5.0"
        assert m.tags == ["t"]
        assert m.content_hash == "abc"


class TestExportSkill:
    def test_export_skill_creates_file(
        self, exchange: SkillExchange, tmp_skills_dir: Path
    ) -> None:
        out = exchange.export_skill("test_pyro_combo", tmp_skills_dir)
        assert out.exists()
        assert out.name == "test_pyro_combo.genshin_skill.json"
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["manifest"]["skill_id"] == "test_pyro_combo"
        assert data["manifest"]["tags"] == ["combat", "pyro"]


class TestImportSkill:
    def test_import_skill_installs(
        self, exchange: SkillExchange, tmp_skills_dir: Path, tmp_path: Path
    ) -> None:
        bundle_path = exchange.export_skill("test_pyro_combo", tmp_skills_dir)
        install_dir = tmp_path / "installed_skills"
        install_dir.mkdir()
        skill_id = exchange.import_skill(bundle_path, install_dir)
        assert skill_id == "test_pyro_combo"
        installed_file = install_dir / "genshin_test_pyro_combo.yaml"
        assert installed_file.exists()
        data = yaml.safe_load(installed_file.read_text(encoding="utf-8"))
        assert "test_pyro_combo" in data["skills"]


class TestValidateBundle:
    def test_validate_valid_bundle(
        self, exchange: SkillExchange, tmp_skills_dir: Path
    ) -> None:
        bundle_path = exchange.export_skill("test_pyro_combo", tmp_skills_dir)
        is_valid, issues = exchange.validate_bundle(bundle_path)
        assert is_valid
        assert issues == []

    def test_validate_invalid_bundle(self, tmp_path: Path) -> None:
        exchange = SkillExchange(exchange_dir=tmp_path / "exchange")
        bad_data = {
            "manifest": {
                "skill_id": "",
                "name": "",
                "version": "",
                "author": "",
                "description": "",
                "created_at": "",
                "game_version": "99.0",
                "tags": [],
                "content_hash": "bad",
            },
            "skill_data": {"foo": "bar"},
            "knowledge_deps": [],
            "profile_requirements": [],
        }
        bad_path = tmp_path / "bad.genshin_skill.json"
        bad_path.write_text(json.dumps(bad_data), encoding="utf-8")
        is_valid, issues = exchange.validate_bundle(bad_path)
        assert not is_valid
        assert len(issues) > 0

    def test_content_hash_verification(
        self, exchange: SkillExchange, tmp_skills_dir: Path
    ) -> None:
        bundle_path = exchange.export_skill("test_pyro_combo", tmp_skills_dir)
        data = json.loads(bundle_path.read_text(encoding="utf-8"))
        data["skill_data"]["tampered"] = True
        bundle_path.write_text(json.dumps(data), encoding="utf-8")
        is_valid, issues = exchange.validate_bundle(bundle_path)
        assert not is_valid
        assert any("hash mismatch" in i.lower() for i in issues)


class TestRoundtrip:
    def test_export_import_roundtrip(
        self, exchange: SkillExchange, tmp_skills_dir: Path, tmp_path: Path
    ) -> None:
        bundle_path = exchange.export_skill("test_pyro_combo", tmp_skills_dir)
        install_dir = tmp_path / "roundtrip_skills"
        install_dir.mkdir()
        skill_id = exchange.import_skill(bundle_path, install_dir)
        assert skill_id == "test_pyro_combo"
        installed_file = install_dir / "genshin_test_pyro_combo.yaml"
        data = yaml.safe_load(installed_file.read_text(encoding="utf-8"))
        orig = yaml.safe_load(
            (tmp_skills_dir / "genshin_test_skills.yaml").read_text(encoding="utf-8")
        )
        assert (
            data["skills"]["test_pyro_combo"]["skill_id"]
            == orig["skills"]["test_pyro_combo"]["skill_id"]
        )
        assert (
            data["skills"]["test_pyro_combo"]["name"]
            == orig["skills"]["test_pyro_combo"]["name"]
        )


class TestListAvailable:
    def test_list_available_empty(self, tmp_path: Path) -> None:
        exchange = SkillExchange(exchange_dir=tmp_path / "exchange")
        assert exchange.list_available() == []

    def test_list_available_after_export(
        self, exchange: SkillExchange, tmp_skills_dir: Path
    ) -> None:
        exchange.export_skill("test_pyro_combo", tmp_skills_dir)
        manifests = exchange.list_available()
        assert len(manifests) == 1
        assert manifests[0].skill_id == "test_pyro_combo"


# ---------------------------------------------------------------------------
# CoOpFilter Tests
# ---------------------------------------------------------------------------


class TestCoOpFilterDefaults:
    def test_coop_filter_not_active_default(self) -> None:
        f = CoOpFilter()
        assert not f.coop_active


class TestCoOpDetection:
    def test_coop_detection(self) -> None:
        f = CoOpFilter()
        # Frame with no blue nameplate regions
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[:, :, 1] = 128
        result = f.detect_coop_mode(frame)
        assert isinstance(result, bool)

    def test_coop_detection_with_blue(self) -> None:
        f = CoOpFilter()
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        # Add blue nameplate-like region (B=200, G<100, R<100 in BGR)
        frame[50:80, 200:400, 0] = 200
        result = f.detect_coop_mode(frame)
        assert isinstance(result, bool)


class TestFilterTeammateDetections:
    def test_filter_teammate_detections(self) -> None:
        f = CoOpFilter()
        f._coop_active = True
        detections: list[tuple[int, int, int, int, float, str]] = [
            (100, 100, 200, 200, 0.9, "enemy"),
            (300, 300, 400, 400, 0.8, "enemy"),
        ]
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        # No teammate bboxes detected in this black frame
        filtered = f.filter_teammate_detections(detections, frame)
        assert len(filtered) == 2


class TestInterferenceScore:
    def test_interference_score_no_overlap(self) -> None:
        f = CoOpFilter()
        target = (0, 0, 100, 100)
        teammates = [(200, 200, 300, 300)]
        score = f.compute_interference_score(target, teammates)
        assert score == 0.0

    def test_interference_score_full_overlap(self) -> None:
        f = CoOpFilter()
        target = (0, 0, 100, 100)
        teammates = [(0, 0, 100, 100)]
        score = f.compute_interference_score(target, teammates)
        assert score == 1.0

    def test_interference_score_no_target(self) -> None:
        f = CoOpFilter()
        score = f.compute_interference_score(None, [(0, 0, 100, 100)])
        assert score == 0.0

    def test_interference_score_no_teammates(self) -> None:
        f = CoOpFilter()
        score = f.compute_interference_score((0, 0, 100, 100), [])
        assert score == 0.0


class TestIoU:
    def test_iou_computation(self) -> None:
        f = CoOpFilter()
        # No overlap
        assert f._iou((0, 0, 50, 50), (100, 100, 200, 200)) == 0.0

        # Identical boxes
        assert f._iou((10, 10, 60, 60), (10, 10, 60, 60)) == pytest.approx(1.0)

        # Partial overlap: a=(0,0,100,100), b=(50,50,150,150)
        # inter = 50*50 = 2500, area_a=10000, area_b=10000, union=17500
        expected = 2500.0 / 17500.0
        assert f._iou((0, 0, 100, 100), (50, 50, 150, 150)) == pytest.approx(expected)

    def test_iou_zero_area(self) -> None:
        f = CoOpFilter()
        assert f._iou((0, 0, 0, 0), (0, 0, 0, 0)) == 0.0
