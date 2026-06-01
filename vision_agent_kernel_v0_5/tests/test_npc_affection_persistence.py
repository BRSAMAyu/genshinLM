"""Tests for NPC affection persistence."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from interaction.dialog_driver import AffectionDialogManager, AffectionLevel
from planning.npc_affection_persistence import NpcAffectionPersistence


@pytest.fixture
def tmp_checkpoint(tmp_path: Path) -> NpcAffectionPersistence:
    manager = AffectionDialogManager()
    return NpcAffectionPersistence(manager, checkpoint_dir=tmp_path, filename="test_affection.json")


class TestNpcAffectionPersistence:

    def test_save_creates_file(self, tmp_path: Path) -> None:
        manager = AffectionDialogManager()
        pers = NpcAffectionPersistence(manager, checkpoint_dir=tmp_path)
        pers.save()
        assert pers.checkpoint_path.exists()

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        manager = AffectionDialogManager()
        pers = NpcAffectionPersistence(manager, checkpoint_dir=tmp_path)

        manager.on_dialog("Katheryne")
        manager.on_quest_complete("Katheryne")
        manager.on_gift("Zhongli")
        manager.on_dialog("Paimon")
        manager.on_dialog("Paimon")
        pers.save()

        manager2 = AffectionDialogManager()
        pers2 = NpcAffectionPersistence(manager2, checkpoint_dir=tmp_path)
        loaded = pers2.load()
        assert loaded is True

        rels = manager2.get_all_relationships()
        assert "Katheryne" in rels
        assert rels["Katheryne"].dialog_count == 1
        assert rels["Katheryne"].quests_completed == 1
        assert rels["Zhongli"].gifts_given == 1
        assert rels["Paimon"].dialog_count == 2

    def test_load_nonexistent_returns_false(self, tmp_path: Path) -> None:
        manager = AffectionDialogManager()
        pers = NpcAffectionPersistence(manager, checkpoint_dir=tmp_path, filename="missing.json")
        assert pers.load() is False

    def test_load_corrupt_file_returns_false(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{")
        manager = AffectionDialogManager()
        pers = NpcAffectionPersistence(manager, checkpoint_dir=tmp_path, filename="bad.json")
        assert pers.load() is False

    def test_reset_single_npc(self, tmp_path: Path) -> None:
        manager = AffectionDialogManager()
        pers = NpcAffectionPersistence(manager, checkpoint_dir=tmp_path)

        manager.on_dialog("Katheryne")
        manager.on_quest_complete("Katheryne")
        manager.on_dialog("Paimon")

        pers.reset("Katheryne")
        rels = manager.get_all_relationships()
        assert rels["Katheryne"].affection == 0
        assert rels["Katheryne"].dialog_count == 0
        assert rels["Paimon"].affection > 0

    def test_reset_all(self, tmp_path: Path) -> None:
        manager = AffectionDialogManager()
        pers = NpcAffectionPersistence(manager, checkpoint_dir=tmp_path)

        manager.on_dialog("Katheryne")
        manager.on_dialog("Paimon")
        pers.reset()
        rels = manager.get_all_relationships()
        assert all(r.affection == 0 for r in rels.values())

    def test_affection_levels_after_load(self, tmp_path: Path) -> None:
        manager = AffectionDialogManager()
        pers = NpcAffectionPersistence(manager, checkpoint_dir=tmp_path)

        # Push affection to FRIEND level (40+)
        for _ in range(10):
            manager.on_quest_complete("Katheryne")
        assert manager.get_level("Katheryne") >= AffectionLevel.FRIEND

        pers.save()
        manager2 = AffectionDialogManager()
        pers2 = NpcAffectionPersistence(manager2, checkpoint_dir=tmp_path)
        pers2.load()
        assert manager2.get_level("Katheryne") >= AffectionLevel.FRIEND

    def test_checkpoint_path_property(self, tmp_path: Path) -> None:
        pers = NpcAffectionPersistence(
            AffectionDialogManager(),
            checkpoint_dir=tmp_path,
            filename="custom.json",
        )
        assert pers.checkpoint_path == tmp_path / "custom.json"

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / "sub" / "dir"
        manager = AffectionDialogManager()
        pers = NpcAffectionPersistence(manager, checkpoint_dir=nested)
        pers.save()
        assert (nested / "npc_affection.json").exists()

    def test_overwrite_existing_checkpoint(self, tmp_path: Path) -> None:
        manager = AffectionDialogManager()
        pers = NpcAffectionPersistence(manager, checkpoint_dir=tmp_path)

        manager.on_dialog("NPC_A")
        pers.save()

        # More interactions
        manager.on_quest_complete("NPC_A")
        manager.on_dialog("NPC_B")
        pers.save()

        manager2 = AffectionDialogManager()
        pers2 = NpcAffectionPersistence(manager2, checkpoint_dir=tmp_path)
        pers2.load()

        rels = manager2.get_all_relationships()
        assert rels["NPC_A"].quests_completed == 1
        assert "NPC_B" in rels
