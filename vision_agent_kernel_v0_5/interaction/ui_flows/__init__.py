"""Predefined UI flows for Genshin Impact menu operations.

Each flow is a UIFlow tuple that can be executed by UIFlowExecutor.
Flows are grouped by game system: character management, inventory,
wish, shop, crafting, etc.
"""
from __future__ import annotations

from interaction.ui_flow_engine import (
    UIFlow,
    UIStep,
    cancel,
    click,
    click_char_tab,
    click_menu_button,
    confirm,
    delay,
    open_menu,
    press,
    scroll,
    wait_loading,
    wait_not_loading,
    wait_state,
)

# ===================================================================
# Paimon menu → submenu flows
# ===================================================================

OPEN_CHARACTER_MENU = UIFlow(
    name="open_character_menu",
    description="Open character management screen via Paimon menu",
    steps=(
        open_menu("open_paimon_menu"),
        delay(300),
        click_menu_button("character", delay_ms=800),
    ),
)

OPEN_BACKPACK = UIFlow(
    name="open_backpack",
    description="Open backpack/inventory via Paimon menu",
    steps=(
        open_menu("open_paimon_menu"),
        delay(300),
        click_menu_button("backpack", delay_ms=800),
    ),
)

OPEN_MAP = UIFlow(
    name="open_map",
    description="Open world map",
    steps=(
        press("m", reason="open_map"),
    ),
)

OPEN_QUEST_MENU = UIFlow(
    name="open_quest_menu",
    description="Open quest menu",
    steps=(
        press("j", reason="open_quest_menu"),
    ),
)

OPEN_PARTY_SETUP = UIFlow(
    name="open_party_setup",
    description="Open party configuration screen",
    steps=(
        press("l", reason="open_party_setup"),
    ),
)

OPEN_WISH = UIFlow(
    name="open_wish",
    description="Open wish/gacha screen",
    steps=(
        press("f3", reason="open_wish"),
        delay(1000),
    ),
)

OPEN_ADVENTURE_HANDBOOK = UIFlow(
    name="open_adventure_handbook",
    description="Open adventurer's handbook",
    steps=(
        press("f1", reason="open_adventure_handbook"),
        delay(500),
    ),
)

OPEN_BATTLE_PASS = UIFlow(
    name="open_battle_pass",
    description="Open battle pass screen",
    steps=(
        press("f4", reason="open_battle_pass"),
        delay(500),
    ),
)

OPEN_EVENTS = UIFlow(
    name="open_events",
    description="Open events panel",
    steps=(
        press("f5", reason="open_events"),
        delay(500),
    ),
)

CLOSE_MENU = UIFlow(
    name="close_menu",
    description="Close current menu/dialog/popup with Escape",
    steps=(
        press("escape", reason="close_menu"),
        delay(300),
    ),
)

# ===================================================================
# Character progression flows
# ===================================================================

CHARACTER_LEVEL_UP = UIFlow(
    name="character_level_up",
    description="Level up the currently selected character (must be on character screen)",
    precondition_state=None,  # checked dynamically
    steps=(
        # Already on character details tab
        click(nx=0.85, ny=0.85, reason="click_level_up_button", delay_ms=300),
        # Material selection popup — auto-filled by game
        click(nx=0.65, ny=0.85, reason="confirm_level_up", delay_ms=500),
    ),
)

CHARACTER_ASCEND = UIFlow(
    name="character_ascend",
    description="Ascend the currently selected character at level cap",
    steps=(
        click(nx=0.85, ny=0.85, reason="click_ascend_button", delay_ms=300),
        # Ascension material popup
        click(nx=0.65, ny=0.85, reason="confirm_ascend", delay_ms=800),
    ),
)

CHARACTER_TALENT_UPGRADE = UIFlow(
    name="character_talent_upgrade",
    description="Upgrade a talent for the currently selected character",
    steps=(
        click_char_tab("talents", delay_ms=500),
        # Click on the talent to select (left talent = normal attack, center = skill, right = burst)
        # Caller should customise these coordinates for the specific talent
        click(nx=0.35, ny=0.50, reason="select_talent", delay_ms=300),
        click(nx=0.85, ny=0.85, reason="click_upgrade_talent", delay_ms=300),
        click(nx=0.65, ny=0.85, reason="confirm_talent_upgrade", delay_ms=500),
    ),
)

# ===================================================================
# Weapon flows
# ===================================================================

WEAPON_EQUIP = UIFlow(
    name="weapon_equip",
    description="Equip a weapon from the weapon list (on character weapon tab)",
    steps=(
        click_char_tab("weapon", delay_ms=500),
        click(nx=0.85, ny=0.50, reason="click_weapon_slot", delay_ms=500),
        # First weapon in list — may need scrolling
        click(nx=0.50, ny=0.35, reason="select_weapon", delay_ms=300),
        click(nx=0.65, ny=0.85, reason="equip_weapon", delay_ms=500),
    ),
)

WEAPON_ENHANCE = UIFlow(
    name="weapon_enhance",
    description="Enhance the equipped weapon (from character weapon tab)",
    steps=(
        click_char_tab("weapon", delay_ms=500),
        click(nx=0.85, ny=0.70, reason="click_enhance_button", delay_ms=500),
        # Auto-fill materials
        click(nx=0.85, ny=0.80, reason="auto_fill_materials", delay_ms=300),
        click(nx=0.65, ny=0.85, reason="confirm_enhance", delay_ms=500),
    ),
)

# ===================================================================
# Artifact flows
# ===================================================================

ARTIFACT_EQUIP = UIFlow(
    name="artifact_equip",
    description="Equip an artifact to an empty slot (on character artifacts tab)",
    steps=(
        click_char_tab("artifacts", delay_ms=500),
        # Click empty slot (center-left area, 5 slots vertically)
        # Caller should customise ny for specific slot (0.30/0.42/0.54/0.66/0.78)
        click(nx=0.35, ny=0.42, reason="click_artifact_slot", delay_ms=500),
        # Select first recommended artifact
        click(nx=0.50, ny=0.35, reason="select_artifact", delay_ms=300),
        click(nx=0.65, ny=0.85, reason="equip_artifact", delay_ms=500),
    ),
)

ARTIFACT_ENHANCE = UIFlow(
    name="artifact_enhance",
    description="Enhance an equipped artifact",
    steps=(
        click_char_tab("artifacts", delay_ms=500),
        click(nx=0.35, ny=0.42, reason="click_artifact_to_enhance", delay_ms=300),
        click(nx=0.85, ny=0.70, reason="click_enhance_button", delay_ms=500),
        click(nx=0.85, ny=0.80, reason="auto_fill_materials", delay_ms=300),
        click(nx=0.65, ny=0.85, reason="confirm_enhance", delay_ms=500),
    ),
)

# ===================================================================
# Party setup flow
# ===================================================================

PARTY_QUICK_CONFIG = UIFlow(
    name="party_quick_config",
    description="Open party config and use quick setup",
    steps=(
        press("l", reason="open_party_setup"),
        delay(800),
        click(nx=0.85, ny=0.85, reason="quick_config_button", delay_ms=500),
    ),
)

# ===================================================================
# Teleport flow (reuses teleport_sequence pattern via UIFlow)
# ===================================================================

TELEPORT_FLOW = UIFlow(
    name="teleport",
    description="Open map, click waypoint area, teleport",
    steps=(
        press("m", reason="open_map"),
        wait_state("map", timeout_ms=3000),
        delay(500),
        # Click center of map (caller should customise for specific waypoint)
        click(nx=0.50, ny=0.50, reason="click_waypoint_area", delay_ms=500),
        # Click teleport button
        click(nx=0.85, ny=0.85, reason="click_teleport_button", delay_ms=300),
        wait_loading(timeout_ms=15000),
        wait_not_loading(timeout_ms=20000),
    ),
)

# ===================================================================
# Domain flow
# ===================================================================

DOMAIN_ENTER_AND_CLAIM = UIFlow(
    name="domain_enter_and_claim",
    description="Enter domain, wait for completion, claim rewards with resin",
    steps=(
        # Interact with domain door
        press("f", reason="interact_domain"),
        delay(500),
        # Start challenge
        click(nx=0.65, ny=0.85, reason="start_challenge", delay_ms=500),
        # Wait for domain to load
        wait_loading(timeout_ms=15000),
        wait_not_loading(timeout_ms=30000),
        # After combat: claim rewards ( Ley Line Blossom )
        delay(1000),
        click(nx=0.50, ny=0.50, reason="click_leyline_blossom", delay_ms=500),
        # Use condensed resin if available, otherwise 20 resin
        click(nx=0.65, ny=0.75, reason="use_condensed_resin", delay_ms=500),
        # Collect rewards
        delay(1000),
        press("escape", reason="exit_domain"),
        wait_loading(timeout_ms=10000),
        wait_not_loading(timeout_ms=15000),
    ),
)

# ===================================================================
# Wish / gacha flow
# ===================================================================

WISH_TEN_PULL = UIFlow(
    name="wish_ten_pull",
    description="Perform a 10-pull on the current banner",
    steps=(
        # Already on wish screen
        click(nx=0.85, ny=0.85, reason="x10_wish_button", delay_ms=500),
        # Confirmation
        click(nx=0.65, ny=0.85, reason="confirm_wish", delay_ms=1000),
        # Wait for animation (skip-able)
        delay(5000),
        press("escape", reason="skip_wish_animation"),
        delay(1000),
        # Results screen — close
        press("escape", reason="close_wish_results"),
        delay(500),
    ),
)

# ===================================================================
# Shop flows
# ===================================================================

SHOP_OPEN_PAIMON_BARGAINS = UIFlow(
    name="shop_open_paimon_bargains",
    description="Navigate to Paimon's Bargains shop",
    steps=(
        open_menu("open_paimon_menu"),
        delay(300),
        click_menu_button("shop", delay_ms=800),
        # Click Paimon's Bargains tab
        click(nx=0.20, ny=0.10, reason="paimon_bargains_tab", delay_ms=500),
    ),
)

SHOP_BUY_MONTHLY_FATES = UIFlow(
    name="shop_buy_monthly_fates",
    description="Buy monthly fates from Paimon's Bargains (stardust shop)",
    steps=(
        # Navigate to stardust exchange tab
        click(nx=0.30, ny=0.10, reason="stardust_exchange_tab", delay_ms=500),
        # Click first intertwined fate
        click(nx=0.35, ny=0.35, reason="select_intertwined_fate", delay_ms=300),
        confirm(reason="buy_fate"),
        delay(500),
        # Click second intertwined fate slot
        click(nx=0.55, ny=0.35, reason="select_intertwined_fate_2", delay_ms=300),
        confirm(reason="buy_fate_2"),
        delay(500),
        # Click acquainted fate
        click(nx=0.35, ny=0.55, reason="select_acquaint_fate", delay_ms=300),
        confirm(reason="buy_acquaint_fate"),
        delay(500),
    ),
)

# ===================================================================
# Crafting / cooking flows
# ===================================================================

CRAFTING_BENCH_INTERACT = UIFlow(
    name="crafting_bench_interact",
    description="Interact with crafting/alchemy bench",
    steps=(
        press("f", reason="interact_crafting_bench"),
        delay(800),
    ),
)

COOKING_INTERACT = UIFlow(
    name="cooking_interact",
    description="Interact with cooking pot",
    steps=(
        press("f", reason="interact_cooking_pot"),
        delay(800),
    ),
)

COOKING_AUTO_COOK = UIFlow(
    name="cooking_auto_cook",
    description="Auto-cook a recipe (must already be on cooking screen with recipe selected)",
    steps=(
        # Select first recipe in list
        click(nx=0.25, ny=0.35, reason="select_recipe", delay_ms=300),
        # Click auto cook
        click(nx=0.65, ny=0.85, reason="auto_cook", delay_ms=500),
        confirm(reason="confirm_cook"),
        delay(500),
    ),
)

# ===================================================================
# Adventure handbook flows
# ===================================================================

HANDBOOK_TRACK_ENEMY = UIFlow(
    name="handbook_track_enemy",
    description="Track an enemy from adventurer's handbook",
    steps=(
        press("f1", reason="open_handbook"),
        delay(500),
        # Click Enemies tab
        click(nx=0.50, ny=0.10, reason="enemies_tab", delay_ms=300),
        # Navigate to enemy list — click first entry
        click(nx=0.30, ny=0.35, reason="select_enemy", delay_ms=300),
        # Click Navigate/Track button
        click(nx=0.65, ny=0.85, reason="track_enemy", delay_ms=300),
        # Close handbook
        press("escape", reason="close_handbook"),
        delay(300),
    ),
)

# ===================================================================
# Time adjustment (some quests require changing time of day)
# ===================================================================

TIME_ADJUST = UIFlow(
    name="time_adjust",
    description="Open time menu and advance time",
    steps=(
        open_menu("open_paimon_menu"),
        delay(300),
        # Click time button
        click(nx=0.20, ny=0.90, reason="time_button", delay_ms=500),
        # Move slider forward
        click(nx=0.70, ny=0.65, reason="move_time_slider", delay_ms=300),
        confirm(reason="confirm_time"),
        delay(1000),
    ),
)

# ===================================================================
# Food usage flows
# ===================================================================

FOOD_USE_FROM_BACKPACK = UIFlow(
    name="food_use_from_backpack",
    description="Use a food item from backpack for healing/buff",
    steps=(
        open_menu("open_paimon_menu"),
        delay(300),
        click_menu_button("backpack", delay_ms=800),
        # Switch to Food tab
        click(nx=0.25, ny=0.08, reason="food_tab", delay_ms=300),
        # Select first food item
        click(nx=0.30, ny=0.30, reason="select_food", delay_ms=300),
        # Use button
        click(nx=0.65, ny=0.85, reason="use_food", delay_ms=300),
    ),
)

# ===================================================================
# Seven Statue interactions
# ===================================================================

STATUE_OFFER_OCULI = UIFlow(
    name="statue_offer_oculi",
    description="Offer collected oculus to Statue of the Seven",
    steps=(
        press("f", reason="interact_statue"),
        delay(800),
        # Click "Offer" option
        click(nx=0.30, ny=0.50, reason="offer_oculi_option", delay_ms=500),
        confirm(reason="confirm_offer"),
        delay(1000),
        press("escape", reason="close_statue_menu"),
    ),
)

# ===================================================================
# Forging flow (U-33)
# ===================================================================

FORGING_INTERACT = UIFlow(
    name="forging_interact",
    description="Interact with blacksmith forge (walk to blacksmith → F)",
    steps=(
        press("f", reason="interact_blacksmith"),
        delay(800),
    ),
)

FORGING_FORGE_ITEM = UIFlow(
    name="forging_forge_item",
    description="Forge an item at the blacksmith (first item in list)",
    steps=(
        # Select first forging recipe
        click(nx=0.25, ny=0.35, reason="select_forge_recipe", delay_ms=300),
        # Click forge button
        click(nx=0.65, ny=0.85, reason="click_forge", delay_ms=500),
        confirm(reason="confirm_forge"),
        delay(1000),
    ),
)

# ===================================================================
# NPC shop purchase flow (U-35)
# ===================================================================

NPC_SHOP_INTERACT = UIFlow(
    name="npc_shop_interact",
    description="Interact with NPC shop (walk to NPC → F)",
    steps=(
        press("f", reason="interact_npc_shop"),
        delay(800),
    ),
)

NPC_SHOP_BUY_ITEM = UIFlow(
    name="npc_shop_buy_item",
    description="Buy an item from NPC shop (first item, quantity 1)",
    steps=(
        # Select first item in shop list
        click(nx=0.30, ny=0.35, reason="select_shop_item", delay_ms=300),
        # Click buy button
        click(nx=0.65, ny=0.85, reason="click_buy", delay_ms=300),
        confirm(reason="confirm_purchase"),
        delay(500),
    ),
)

# ===================================================================
# Quick food usage in combat (U-42)
# ===================================================================

COMBAT_FOOD_REVIVE = UIFlow(
    name="combat_food_revive",
    description="Quick-use revive food from food menu during combat",
    steps=(
        # Open food quick-menu (press food key or navigate)
        press("escape", reason="open_menu_for_food"),
        delay(300),
        click_menu_button("backpack", delay_ms=500),
        click(nx=0.25, ny=0.08, reason="food_tab", delay_ms=300),
        # Select revive food (first item)
        click(nx=0.30, ny=0.30, reason="select_revive_food", delay_ms=300),
        click(nx=0.65, ny=0.85, reason="use_revive_food", delay_ms=300),
        # Select downed character
        click(nx=0.50, ny=0.50, reason="select_downed_character", delay_ms=300),
    ),
)

# ===================================================================
# Element resonance at Statue (U-44)
# ===================================================================

STATUE_ELEMENT_RESONANCE = UIFlow(
    name="statue_element_resonance",
    description="Change Traveler element at Statue of the Seven",
    steps=(
        press("f", reason="interact_statue"),
        delay(800),
        # Click "Resonate with [Element]" option
        click(nx=0.50, ny=0.60, reason="resonate_with_element", delay_ms=500),
        confirm(reason="confirm_resonance"),
        delay(1000),
        press("escape", reason="close_statue_menu"),
    ),
)

# ===================================================================
# U-54: Batch artifact locking
# ===================================================================

ARTIFACT_BATCH_LOCK = UIFlow(
    name="artifact_batch_lock",
    description="Batch lock artifacts by rarity and score",
    steps=(
        open_menu("open_paimon_menu"),
        delay(300),
        click_menu_button("backpack", delay_ms=800),
        click(nx=0.25, ny=0.08, reason="artifact_tab", delay_ms=300),
        # Scroll to artifacts
        scroll(-3, reason="scroll_to_artifacts"),
        delay(200),
        # Select first artifact
        click(nx=0.30, ny=0.30, reason="select_artifact_1", delay_ms=100),
        click(nx=0.30, ny=0.40, reason="select_artifact_2", delay_ms=100),
        click(nx=0.30, ny=0.50, reason="select_artifact_3", delay_ms=100),
        # Lock button
        click(nx=0.85, ny=0.85, reason="batch_lock", delay_ms=300),
        confirm(reason="confirm_lock"),
        delay(300),
    ),
)

# ===================================================================
# U-55: Weapon refinement flow
# ===================================================================

WEAPON_REFINE = UIFlow(
    name="weapon_refine",
    description="Refine equipped weapon using duplicate",
    steps=(
        press("l", reason="open_party_setup"),
        delay(800),
        click(nx=0.35, ny=0.35, reason="select_character", delay_ms=500),
        click_char_tab("weapon", delay_ms=300),
        # Click on weapon
        click(nx=0.35, ny=0.40, reason="select_weapon", delay_ms=300),
        # Click refine option
        click(nx=0.85, ny=0.60, reason="click_refine", delay_ms=300),
        # Select duplicate if available
        click(nx=0.50, ny=0.35, reason="select_duplicate", delay_ms=200),
        confirm(reason="confirm_refine"),
        delay(500),
        press("escape", reason="close_party"),
    ),
)

# ===================================================================
# U-56: Synthesis quantity selection
# ===================================================================

SYNTHESIS_SELECT_QUANTITY = UIFlow(
    name="synthesis_select_quantity",
    description="Select synthesis quantity (1, 5, or max)",
    steps=(
        press("f", reason="interact_crafting_bench"),
        delay(800),
        click(nx=0.25, ny=0.35, reason="select_recipe", delay_ms=300),
        # Click quantity selector
        click(nx=0.65, ny=0.50, reason="open_quantity_selector", delay_ms=300),
        # Select max (5th option)
        click(nx=0.65, ny=0.70, reason="select_max_quantity", delay_ms=200),
        confirm(reason="confirm_synthesis"),
        delay(500),
    ),
)

# ===================================================================
# U-57: Forge weapon type selection
# ===================================================================

FORGE_WEAPON_SELECT_TYPE = UIFlow(
    name="forge_weapon_select_type",
    description="Select weapon type when forging",
    steps=(
        press("f", reason="interact_blacksmith"),
        delay(800),
        # Click Forge tab
        click(nx=0.25, ny=0.10, reason="forge_tab", delay_ms=300),
        # Select weapon type (e.g., sword)
        click(nx=0.30, ny=0.35, reason="select_sword_type", delay_ms=300),
        # Select specific weapon
        click(nx=0.35, ny=0.50, reason="select_weapon", delay_ms=200),
        # Set quantity to 1
        click(nx=0.65, ny=0.60, reason="select_quantity_1", delay_ms=200),
        confirm(reason="confirm_forge"),
        delay(1000),
    ),
)

# ===================================================================
# U-58~U-59: Waypoint navigation with precision and tolerance
# ===================================================================

WAYPOINT_NAVIGATE_PRECISE = UIFlow(
    name="waypoint_navigate_precise",
    description="Navigate to waypoint with precision and coordinate tolerance",
    steps=(
        press("m", reason="open_map"),
        wait_state("map", timeout_ms=3000),
        delay(500),
        # Click waypoint with position tolerance
        click(nx=0.50, ny=0.45, reason="click_waypoint", delay_ms=500),
        # Wait for waypoint info
        wait_state("waypoint_info", timeout_ms=2000),
        delay(300),
        # Click teleport (with coordinate tolerance ±5px)
        click(nx=0.85, ny=0.85, reason="click_teleport", delay_ms=300),
        wait_loading(timeout_ms=15000),
        wait_not_loading(timeout_ms=20000),
    ),
)

# ===================================================================
# U-61: Star rarity detection
# ===================================================================

RARITY_DETECT_STAR = UIFlow(
    name="rarity_detect_star",
    description="Detect item rarity by star count",
    steps=(
        # On item detail screen
        click(nx=0.50, ny=0.50, reason="open_item_detail", delay_ms=500),
        # Read star indicators
        # (This flow triggers OCR - actual detection is in perception module)
        delay(1000),
    ),
)

# ===================================================================
# U-62: Backpack multi-select
# ===================================================================

BACKPACK_MULTI_SELECT = UIFlow(
    name="backpack_multi_select",
    description="Multi-select items in backpack for batch operations",
    steps=(
        open_menu("open_paimon_menu"),
        delay(300),
        click_menu_button("backpack", delay_ms=800),
        # Enable multi-select mode
        click(nx=0.80, ny=0.10, reason="multi_select_button", delay_ms=300),
        # Select multiple items
        click(nx=0.30, ny=0.30, reason="select_item_1", delay_ms=100),
        click(nx=0.30, ny=0.40, reason="select_item_2", delay_ms=100),
        click(nx=0.30, ny=0.50, reason="select_item_3", delay_ms=100),
        click(nx=0.30, ny=0.60, reason="select_item_4", delay_ms=100),
        # Execute batch action
        click(nx=0.85, ny=0.85, reason="batch_action", delay_ms=300),
    ),
)

# ===================================================================
# U-63: Team lock
# ===================================================================

TEAM_LOCK_ACTIVE = UIFlow(
    name="team_lock_active",
    description="Lock current team configuration",
    steps=(
        press("l", reason="open_party_setup"),
        delay(800),
        # Click lock team button
        click(nx=0.85, ny=0.15, reason="lock_team_button", delay_ms=300),
        confirm(reason="confirm_lock_team"),
        delay(500),
        press("escape", reason="close_party"),
    ),
)

# ===================================================================
# U-64: Team formation success verification
# ===================================================================

TEAM_FORMATION_VERIFY = UIFlow(
    name="team_formation_verify",
    description="Verify team formation completed successfully",
    steps=(
        press("l", reason="open_party_setup"),
        delay(800),
        # Set team members
        click(nx=0.30, ny=0.30, reason="select_char_1", delay_ms=200),
        click(nx=0.40, ny=0.30, reason="select_char_2", delay_ms=200),
        click(nx=0.50, ny=0.30, reason="select_char_3", delay_ms=200),
        click(nx=0.60, ny=0.30, reason="select_char_4", delay_ms=200),
        # Verify team
        wait_state("team_verified", timeout_ms=2000),
        delay(300),
        press("escape", reason="close_party"),
    ),
)

# ===================================================================
# Forged flows registry addition
# ===================================================================

ALL_FLOWS: dict[str, UIFlow] = {
    f.name: f for f in [
        OPEN_CHARACTER_MENU,
        OPEN_BACKPACK,
        OPEN_MAP,
        OPEN_QUEST_MENU,
        OPEN_PARTY_SETUP,
        OPEN_WISH,
        OPEN_ADVENTURE_HANDBOOK,
        OPEN_BATTLE_PASS,
        OPEN_EVENTS,
        CLOSE_MENU,
        CHARACTER_LEVEL_UP,
        CHARACTER_ASCEND,
        CHARACTER_TALENT_UPGRADE,
        WEAPON_EQUIP,
        WEAPON_ENHANCE,
        ARTIFACT_EQUIP,
        ARTIFACT_ENHANCE,
        PARTY_QUICK_CONFIG,
        TELEPORT_FLOW,
        DOMAIN_ENTER_AND_CLAIM,
        WISH_TEN_PULL,
        SHOP_OPEN_PAIMON_BARGAINS,
        SHOP_BUY_MONTHLY_FATES,
        CRAFTING_BENCH_INTERACT,
        COOKING_INTERACT,
        COOKING_AUTO_COOK,
        HANDBOOK_TRACK_ENEMY,
        TIME_ADJUST,
        FOOD_USE_FROM_BACKPACK,
        STATUE_OFFER_OCULI,
        FORGING_INTERACT,
        FORGING_FORGE_ITEM,
        NPC_SHOP_INTERACT,
        NPC_SHOP_BUY_ITEM,
        COMBAT_FOOD_REVIVE,
        STATUE_ELEMENT_RESONANCE,
        # New flows
        ARTIFACT_BATCH_LOCK,
        WEAPON_REFINE,
        SYNTHESIS_SELECT_QUANTITY,
        FORGE_WEAPON_SELECT_TYPE,
        WAYPOINT_NAVIGATE_PRECISE,
        RARITY_DETECT_STAR,
        BACKPACK_MULTI_SELECT,
        TEAM_LOCK_ACTIVE,
        TEAM_FORMATION_VERIFY,
    ]
}


def get_flow(name: str) -> UIFlow:
    """Look up a predefined flow by name."""
    flow = ALL_FLOWS.get(name)
    if flow is None:
        raise KeyError(f"unknown flow: {name!r}. Known: {sorted(ALL_FLOWS)}")
    return flow
