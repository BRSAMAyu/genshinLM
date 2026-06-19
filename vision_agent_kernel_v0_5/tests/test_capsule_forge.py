"""Tests for app_service/capsule_forge.py: CapsuleForge skeleton generator."""
from __future__ import annotations

import json

import pytest
import yaml

from app_service.capsule_forge import CapsuleForge


class TestCapsuleForgeCreation:
    def test_creates_directory_structure(self, tmp_path):
        result = CapsuleForge().forge("my_game", output_dir=str(tmp_path / "my_game"))

        assert (tmp_path / "my_game" / "capsule.yaml").is_file()
        assert (tmp_path / "my_game" / "keymap.yaml").is_file()
        assert (tmp_path / "my_game" / "skills" / "index.json").is_file()
        assert result.game_id == "my_game"
        assert len(result.files_created) == 6
        assert (tmp_path / "my_game" / "detectors" / "my_game_screen_classifier.py").is_file()
        assert (tmp_path / "my_game" / "detectors" / "my_game_combat_detector.py").is_file()
        assert (tmp_path / "my_game" / "providers" / "my_game_provider.py").is_file()

    def test_default_output_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CapsuleForge().forge("testgame")

        expected = tmp_path / "capsules" / "testgame"
        assert result.capsule_dir == expected
        assert expected.is_dir()

    def test_validation_rejects_empty_name(self):
        with pytest.raises(ValueError, match="non-empty"):
            CapsuleForge().forge("")

    def test_validation_rejects_special_chars(self):
        with pytest.raises(ValueError, match="non-empty"):
            CapsuleForge().forge("!@#$%")

    def test_idempotent_run(self, tmp_path):
        forge = CapsuleForge()
        out = str(tmp_path / "idem_game")
        r1 = forge.forge("idem_game", output_dir=out)
        r2 = forge.forge("idem_game", output_dir=out)

        assert r1.game_id == r2.game_id
        assert r1.capsule_dir == r2.capsule_dir

    def test_custom_output_dir(self, tmp_path):
        custom = tmp_path / "custom_location" / "my_rpg"
        result = CapsuleForge().forge("my_rpg", output_dir=str(custom))

        assert custom.is_dir()
        assert (custom / "capsule.yaml").is_file()
        assert result.game_id == "my_rpg"

    def test_yaml_manifest_structure(self, tmp_path):
        CapsuleForge().forge("cool_game", output_dir=str(tmp_path / "cool_game"))

        with open(tmp_path / "cool_game" / "capsule.yaml", encoding="utf-8") as f:
            manifest = yaml.safe_load(f)

        assert manifest["capsule_id"] == "cool_game"
        assert manifest["display_name"] == "cool_game"
        assert manifest["version"] == "0.1.0"
        assert manifest["keymap_file"] == "keymap.yaml"
        assert isinstance(manifest["detectors"], list)
        assert len(manifest["detectors"]) >= 1
        assert manifest["detectors"][0]["id"] == "cool_game_screen_classifier"
        assert manifest["skills_file"] == "skills/index.json"

    def test_keymap_has_standard_bindings(self, tmp_path):
        CapsuleForge().forge("kgame", output_dir=str(tmp_path / "kgame"))

        with open(tmp_path / "kgame" / "keymap.yaml", encoding="utf-8") as f:
            keymap = yaml.safe_load(f)

        assert keymap["move_forward"] == "W"
        assert keymap["jump"] == "Space"
        assert keymap["menu"] == "Escape"
        assert keymap["map"] == "Tab"

    def test_skill_index_is_valid_empty_json(self, tmp_path):
        CapsuleForge().forge("sgame", output_dir=str(tmp_path / "sgame"))

        with open(tmp_path / "sgame" / "skills" / "index.json", encoding="utf-8") as f:
            data = json.load(f)

        assert isinstance(data["skills"], list)
        assert len(data["skills"]) >= 1
        assert data["skills"][0]["id"].startswith("sgame_")

    def test_sanitizes_display_name_to_id(self, tmp_path):
        result = CapsuleForge().forge("My Cool Game 2", output_dir=str(tmp_path / "m"))

        assert result.game_id == "My_Cool_Game_2"

    def test_underscore_only_name_rejected(self):
        with pytest.raises(ValueError, match="non-empty"):
            CapsuleForge().forge("___")
