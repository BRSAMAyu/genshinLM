"""Integration tests: KernelSkillRecipeLookup wired to GameCapsule.skill_library()."""
from __future__ import annotations

from agent_kernel.skill_lookup import KernelSkillRecipeLookup
from agent_kernel.types import SkillRecipe
from capsules.genshin.genshin_game_capsule import GenshinGameCapsule


class TestSkillLookupFromCapsule:

    def test_genshin_capsule_skills_load_into_lookup(self) -> None:
        capsule = GenshinGameCapsule()
        library = capsule.skill_library()
        assert len(library) > 0

        lookup = KernelSkillRecipeLookup.from_capsule_library(library)
        assert len(lookup) > 0

    def test_lookup_by_capability(self) -> None:
        capsule = GenshinGameCapsule()
        lookup = KernelSkillRecipeLookup.from_capsule_library(capsule.skill_library())

        first_capability = next(iter(capsule.skill_library()))
        recipe = lookup.lookup(first_capability)
        assert isinstance(recipe, SkillRecipe)

    def test_lookup_recipe_by_skill_id(self) -> None:
        capsule = GenshinGameCapsule()
        library = capsule.skill_library()
        lookup = KernelSkillRecipeLookup.from_capsule_library(library)

        first_cap, first_recipe = next(iter(library.items()))
        result = lookup.lookup_recipe(first_recipe.skill_id)
        assert isinstance(result, dict)

    def test_all_capsule_skills_are_valid_recipes(self) -> None:
        capsule = GenshinGameCapsule()
        library = capsule.skill_library()

        for capability, recipe in library.items():
            assert isinstance(recipe, SkillRecipe), f"{capability} is not a SkillRecipe"
            assert recipe.skill_id, f"{capability} has empty skill_id"
            assert recipe.title, f"{capability} has empty title"
