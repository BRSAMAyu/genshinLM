"""Tests for runtime/account_state.py: account state data model, serialization, persistence."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from runtime.account_state import (
    AccountState,
    CharacterInfo,
    DailyCompletion,
    LocationState,
    QuestProgress,
    ResourceState,
    TeamSlot,
    WeaponInfo,
    WeeklyCompletion,
)


class TestCharacterInfo:
    def test_to_dict(self):
        c = CharacterInfo(character_id="xiangling", level=80, constellation=6)
        d = c.to_dict()
        assert d["character_id"] == "xiangling"
        assert d["level"] == 80
        assert d["constellation"] == 6
        assert d["talents"]["normal_attack"] == 1

    def test_talents_tuple(self):
        c = CharacterInfo(character_id="amber", talents=(6, 8, 6))
        d = c.to_dict()
        assert d["talents"]["elemental_skill"] == 8


class TestWeaponInfo:
    def test_to_dict(self):
        w = WeaponInfo(weapon_id="the_catch", level=90, refinement_rank=5)
        d = w.to_dict()
        assert d["weapon_id"] == "the_catch"
        assert d["refinement_rank"] == 5


class TestResourceState:
    def test_to_dict(self):
        r = ResourceState(original_resin=120, mora=500000)
        d = r.to_dict()
        assert d["original_resin"] == 120
        assert d["mora"] == 500000


class TestQuestProgress:
    def test_to_dict(self):
        q = QuestProgress(quest_id="ch1_act2", current_step_index=7, status="in_progress")
        d = q.to_dict()
        assert d["quest_id"] == "ch1_act2"
        assert d["status"] == "in_progress"


class TestLocationState:
    def test_to_dict(self):
        loc = LocationState(region="liyue", subregion="mt_tianheng")
        d = loc.to_dict()
        assert d["region"] == "liyue"


class TestAccountState:
    def test_to_dict(self):
        state = AccountState(
            uid="123456789", server="asia01", ar=35, world_level=4,
            characters=[CharacterInfo(character_id="xiangling", level=80)],
            unlocked_regions=["mondstadt", "liyue"],
        )
        d = state.to_dict()
        assert d["uid"] == "123456789"
        assert d["ar"] == 35
        assert len(d["characters"]) == 1
        assert d["characters"][0]["character_id"] == "xiangling"
        assert d["unlocked_regions"] == ["mondstadt", "liyue"]

    def test_from_dict_roundtrip(self):
        original = AccountState(
            uid="987654321", server="cn01", ar=45, world_level=6,
            characters=[
                CharacterInfo(character_id="xiangling", level=90, talents=(8, 12, 8)),
            ],
            weapons=[WeaponInfo(weapon_id="the_catch", level=90, refinement_rank=5)],
            resources=ResourceState(original_resin=80, mora=2000000),
            location=LocationState(region="inazuma"),
            active_quest=QuestProgress(quest_id="ch2_act1", status="in_progress"),
            active_team=(
                TeamSlot(character_id="xiangling", role="main_dps"),
                TeamSlot(character_id="xingqiu", role="sub_dps"),
            ),
            archon_quest_progress={"prologue": "completed"},
        )
        d = original.to_dict()
        restored = AccountState.from_dict(d, store_dir=Path("test_accounts"))

        assert restored.uid == original.uid
        assert restored.ar == original.ar
        assert restored.world_level == original.world_level
        assert len(restored.characters) == 1
        assert restored.characters[0].level == 90
        assert restored.characters[0].talents == (8, 12, 8)
        assert len(restored.weapons) == 1
        assert restored.weapons[0].refinement_rank == 5
        assert restored.resources.original_resin == 80
        assert restored.location.region == "inazuma"
        assert restored.active_quest.quest_id == "ch2_act1"
        assert len(restored.active_team) == 2
        assert restored.archon_quest_progress["prologue"] == "completed"

    def test_save_and_load(self):
        test_dir = Path("test_account_state_dir")
        if test_dir.exists():
            shutil.rmtree(test_dir)

        state = AccountState(
            uid="123456789", ar=35, store_dir=test_dir,
            characters=[CharacterInfo(character_id="amber", level=40)],
        )
        state.save()

        loaded = AccountState.load(test_dir)
        assert loaded.uid == "123456789"
        assert loaded.ar == 35
        assert len(loaded.characters) == 1
        assert loaded.characters[0].character_id == "amber"

        shutil.rmtree(test_dir)

    def test_load_missing_creates_default(self):
        test_dir = Path("test_account_missing")
        # Ensure clean state
        if test_dir.exists():
            shutil.rmtree(test_dir)

        state = AccountState.load(test_dir)
        assert state.uid == ""
        assert state.ar == 0

        # Directory may not be created (no save was called)
        if test_dir.exists():
            shutil.rmtree(test_dir)

    def test_atomic_write_no_corrupt_on_partial(self):
        test_dir = Path("test_account_atomic")
        if test_dir.exists():
            shutil.rmtree(test_dir)

        state = AccountState(uid="atomic_test", ar=50, store_dir=test_dir)
        state.save()

        # Verify JSON is valid
        with open(test_dir / "account_state.json") as f:
            data = json.load(f)
        assert data["uid"] == "atomic_test"

        shutil.rmtree(test_dir)


class TestUpdateHelpers:
    def test_update_resources(self):
        state = AccountState()
        assert state.resources.original_resin == 160
        state.update_resources(original_resin=80, mora=500000)
        assert state.resources.original_resin == 80
        assert state.resources.mora == 500000

    def test_update_location(self):
        state = AccountState()
        state.update_location(region="liyue", subregion="qingce")
        assert state.location.region == "liyue"
        assert state.location.subregion == "qingce"

    def test_update_quest(self):
        state = AccountState()
        state.update_quest(quest_id="ch1_act1", step_index=5, status="in_progress")
        assert state.active_quest.quest_id == "ch1_act1"
        assert state.active_quest.current_step_index == 5
        assert state.active_quest.status == "in_progress"

    def test_update_resources_preserves_other_fields(self):
        state = AccountState(resources=ResourceState(original_resin=100, mora=300000))
        state.update_resources(original_resin=50)
        assert state.resources.original_resin == 50
        assert state.resources.mora == 300000

    def test_update_location_partial(self):
        state = AccountState(location=LocationState(region="mondstadt"))
        state.update_location(subregion="whispering_woods")
        assert state.location.region == "mondstadt"
        assert state.location.subregion == "whispering_woods"
