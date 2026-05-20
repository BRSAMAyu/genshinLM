# Genshin Impact (原神) UI Visual Reference for Vision Agent Development

**Research Date:** 2026-05-20
**Game Version:** ~5.x / 6.x era
**Companion Document:** See `genshin_impact_technical_specs.md` for input system, anti-cheat, performance, and co-op details.

---

## 1. Main Game HUD (Overworld Gameplay Screen)

### 1.1 Layout Overview (1920x1080 reference)

```
+------------------------------------------------------------------+
|  [Minimap]          [Quest Tracker]     [Party Info]    [Paimon]  |
|   (top-left)          (top-right        (top-right     (top-right|
|                        area)           corner)         corner)   |
|                                                                    |
|                                                                    |
|                                                                    |
|                     [3D GAME WORLD]                                |
|                                                                    |
|                                                                    |
|                                                                    |
|  [Current    [Elemental        [Skill Buttons]  [Party Portraits] |
|   Char HP]    Sight/Nav]       (bottom-right)   (right side)      |
|  (bottom-    (center)                                             |
|   center)                                                          |
+------------------------------------------------------------------+
```

### 1.2 Detailed Element Positions (at 1920x1080)

#### TOP-LEFT: Minimap Region
- **Minimap (circular)**: Top-left corner, approximately 200x200 pixel area
  - Position: ~(20, 20) to ~(220, 220)
  - Circular shape with border ring
  - Displays: terrain, player arrow, NPC dots, quest markers
  - **Minimap mode settings**: "Rotating" (top = current view) or "Fixed" (top = North)
  - Clicking the minimap opens the full-screen World Map (hotkey: M)
- **Around the minimap ring**: Several small icon buttons:
  - **Current time** display (day/night cycle)
  - **Weather** indicator
  - **Quest navigation** tracker
  - Hold Alt + click to interact with these icons on PC

#### TOP-RIGHT: Party & System Info
- **Party member info** (active character): Character name, level, constellation count
- **Paimon menu button**: Top-right corner, always visible. Press Esc or click to open
- **Quick-access icons** arranged around the minimap and top-right:
  - Mail notification (red dot when unread)
  - Event notifications
  - Various status indicators

#### RIGHT SIDE: Party Portraits (In-Combat / Overworld)
- **3 inactive party member portraits** displayed vertically on the right side
  - Each portrait is a **circular image** (~60-80px diameter) of the character's face
  - **Element indicator**: Color-coded ring around portrait (Pyro=orange, Hydro=blue, Electro=purple, Cryo=light-blue, Anemo=teal, Geo=amber, Dendro=green)
  - **HP bar**: Thin bar beneath each portrait (green when healthy, yellow/red when damaged)
  - **Press 1/2/3/4** keys to switch to that character (1 = active, 2/3/4 = portraits)
  - Portraits glow/pulse when their Elemental Burst is fully charged
  - Number labels visible on each portrait

#### BOTTOM-CENTER: Active Character Status
- **HP Bar**: Prominent horizontal bar, center-bottom area
  - Green when HP > 50%, transitions to yellow then red as HP decreases
  - Displays exact HP numbers (current/max)
  - Approximately 300-400px wide
- **Energy gauge**: Circular or arc indicator near the HP bar
  - Shows Elemental Burst energy charge (0-100%)
  - Glows when fully charged

#### BOTTOM-RIGHT: Combat Skill Buttons
The skill button cluster in bottom-right has this approximate layout:

```
                    [Burst (Q)]     [Skill (E)]
                        |               |
                    (large icon)    (large icon)
                        |
                   [Attack (LMB)]
                   [Sprint]  [Jump]
```

- **Elemental Burst (Q)**: Larger circular icon, character-specific art. Shows energy fill state. Greyed out when insufficient energy. Glows with element color when ready.
- **Elemental Skill (E)**: Circular icon with character-specific skill art. Shows cooldown timer (circular sweep animation) when on cooldown.
- **Normal Attack**: Not shown as a persistent button on PC (Left Click). On mobile, it is a visible button.
- **Sprint** / **Jump**: Not shown as persistent buttons on PC keyboard. Visible on mobile/controller layouts.
- **Important visual cues**:
  - Skill on cooldown: Dimmed icon with countdown number overlay
  - Burst ready: Bright glow, element-colored particles
  - Burst not ready: Grey/dimmed, energy arc partially filled

#### CENTER-BOTTOM: Interaction Prompt
- **"F" key prompt**: Appears near the character when near interactable objects
  - Shows key icon (F) + action text (e.g., "Talk", "Open", "Collect", "Mine")
  - Semi-transparent background panel
  - Position: roughly screen center, slightly below middle

#### CENTER: Navigation / Quest Markers
- **Quest Navigation arrow**: Center of screen, points toward tracked quest objective
  - Yellow/gold arrow pointing in the direction of the objective
  - Shows distance number
  - Visible during overworld exploration

---

## 2. Menu Screens

### 2.1 Paimon Menu (Main Menu Overlay)
- **Opened by**: Esc key (PC) or clicking Paimon icon (top-right)
- **Layout**: Semi-circular or grid arrangement of menu icons overlaid on a dimmed game view
- **Background**: Game world visible but darkened/frosted glass effect
- **Paimon**: Animated character appears, floating
- **Menu items** (arranged in a radial/grid pattern):
  - Inventory (Bag)
  - Character
  - Party Setup
  - Adventurer Handbook
  - Map
  - Friends
  - Co-Op Mode
  - Mail
  - Events
  - Battle Pass
  - Wish
  - Shop
  - Settings (gear icon)
  - Archive
  - Notices
  - Photo Mode (camera icon)
- **Version-specific**: The exact layout changed significantly in v3.0, v4.0, and v5.0
- **Close**: Press Esc again or click the back/close button

### 2.2 Inventory Screen
- **Layout**: Left sidebar with category tabs, right area shows item grid
- **Categories (left tabs)**:
  - Weapons
  - Artifacts
  - Character Development Items
  - Materials
  - Gadgets
  - Quest Items
  - Precious Items
  - Furnishings
- **Item grid**: 5-6 columns, scrollable rows of item icons
  - Rarity shown by background color (1-star grey to 5-star gold)
  - Quantity number overlay on stackable items
  - Equipped indicator on weapons/artifacts currently in use
  - **Red exclamation mark** on new/unviewed items
  - Lock icon on locked items
- **Sorting**: By level, rarity, quantity (ascending/descending)
- **Bottom area**: Selected item details, stats, description

### 2.3 Character Screen
- **Access**: Hotkey C or Paimon Menu > Character
- **Layout**: Full-screen with character model displayed center-left
- **Left sidebar tabs**:
  - **Attributes**: Character stats overview (HP, ATK, DEF, Elemental Mastery, Crit Rate, Crit DMG, Energy Recharge)
  - **Weapons**: Weapon slot with stats, equip/upgrade options
  - **Artifacts**: 5 artifact slots (Flower, Plume, Sands, Goblet, Circlet) with equip/upgrade
  - **Constellation**: 6 constellation nodes, character-specific bonuses
  - **Talents**: Normal Attack, Elemental Skill, Elemental Burst + passive talents. Upgrade levels shown.
  - **Profile**: Character lore, voice-overs, namecard
- **Character selection**: Top bar or left panel with all owned characters
  - Element icon, level, constellation count visible
  - Currently equipped weapon/artifact summary

### 2.4 Party Setup Screen
- **Access**: Hotkey L or Paimon Menu > Party Setup
- **Layout** (v4.0+ redesign):
  - 4 character slots displayed prominently (active party)
  - Character select panel below/adjacent with all owned characters
  - **Background**: Changes based on current region (Mondstadt, Liyue, Inazuma, etc.) or default
  - Can be toggled in Settings > Other
- **Controls**:
  - Drag-and-drop characters into slots
  - Quick swap button for each slot
  - Support character selection (for co-op/domains)
- **Support character**: 5th slot for Abyss/domain support picks

### 2.5 Adventurer Handbook
- **Access**: Hotkey F1
- **Tabs/Chapters**:
  - **Chapters of Experience**: Guided tasks with rewards (early game progression)
  - **Embattle**: Team composition recommendations
  - **Commissions**: Daily commission tracker
  - **Domains**: Dungeon recommendations by day
  - **Bosses**: Weekly and normal boss tracking
  - **Enemies**: Monster handbook entries
  - **Materials**: Material source lookup
  - **Living Beings**: Wildlife and fishing catalog
  - **Tutorials**: Game mechanic tutorials
  - **Travel Log**: Archon Quest and Story Quest dialogue log
- **Visual layout**: Book-style interface with page-turning animation
  - Tab icons along the top or side
  - Content area in center with list/grid entries
  - **Claim Reward** buttons appear as gold/amber rectangular buttons when tasks are completed

### 2.6 Crafting / Forging / Cooking Screens
- **Crafting (Alchemy)**:
  - Central crafting bench with ingredient slots
  - Available recipes listed on left/top
  - Material requirements shown on right
  - **Craft** button (prominent gold button) at bottom
  - Quantity selector (+/- or type number)
- **Forging (Blacksmith)**:
  - Similar layout to crafting
  - Forge timer visible for some items
  - Material cost and forging time displayed
  - **Forge** button at bottom
- **Cooking**:
  - Recipe list on left
  - Cooking mini-game area in center (indicator bar with sweet spot)
  - Ingredient requirements on right
  - Manual cook / Auto cook buttons
  - Proficiency bar per recipe (mastering recipe = auto cook available)

---

## 3. Dialog System

### 3.1 NPC Dialog Layout
- **Dialog box**: Bottom-center of the screen
  - Semi-transparent dark panel, approximately bottom 25-30% of screen
  - Width: ~60-70% of screen width, centered
- **Speaker name**: Displayed at the top of the dialog box, often in a stylized nameplate
- **Speaker portrait**: Character portrait on the left or right side of the dialog text
  - Expression changes based on dialog mood
- **Dialog text**: White text on the semi-transparent background
  - Text appears with a typewriter animation (character by character)
  - Supports rich formatting (colored text for item names, etc.)

### 3.2 Dialog Choice Buttons
- When dialog offers choices, **2-4 option buttons** appear:
  - Positioned above or overlapping the dialog box
  - **Rounded rectangular buttons** with text
  - Semi-transparent background with lighter border
  - Numbered (1, 2, 3...) for keyboard selection
  - Hovered option highlights with a brighter background
- Choices are always vertically stacked

### 3.3 Auto / Skip Controls
- **Auto button**: Located in the dialog box area
  - Toggles auto-advance mode (text scrolls automatically)
  - Small button, often in the bottom-right corner of the dialog panel
- **No full skip button exists** (as of v6.x):
  - Players must rapidly click/tap to advance through dialog
  - There is a cooldown between clicks (~0.3-0.5 seconds)
  - Community has requested a skip button for 4+ years; not yet implemented
- **Cutscenes**: Some story cutscenes have a "Skip" button
  - Appears as a small button in the corner (bottom-right typically)
  - Prompts a confirmation dialog before skipping

### 3.4 Dialog Completion Indicator
- Dialog ends when the dialog box disappears and the NPC interaction prompt returns
- Some dialogs end with a quest update notification (top-right area)

---

## 4. Notifications and Popups

### 4.1 Daily Commission Completion
- **Popup style**: Slide-in notification from the right side
  - Gold/amber banner with commission name
  - "Commission Complete" text
  - Reward summary (Primogems, Mora, Adventure EXP, etc.)
  - **Claim** button or auto-claimed
- **All 4 commissions complete**: Additional "All Daily Commissions Completed" popup
  - Larger notification with total reward summary

### 4.2 Achievement Notifications
- **Slide-in from the right** side of screen
- Achievement icon + achievement name
- "Achievement Unlocked" text with a distinctive chime
- Shows Primogem reward amount
- Auto-dismisses after ~3-5 seconds
- Can be viewed later in the Achievements menu

### 4.3 Resin Refill / Original Resin Prompts
- **Resin full notification** (160/160 or 200/200):
  - Push notification on mobile
  - In-game: small icon reminder near the minimap area
  - Can be configured in Settings > Messages > "Original Resin if fully replenished"
- **Resin insufficient popup**:
  - Modal dialog when attempting resin-consuming activity without enough resin
  - Shows current resin, required amount
  - Option to use Fragile Resin or Condensed Resin

### 4.4 Battle Pass Notifications
- **Level up notification**: Slide-in popup when BP level increases
  - Shows new level and available rewards
- **BP reward claim**: Must be manually claimed from Battle Pass screen
  - Unclaimed rewards show red dot indicator on BP icon in Paimon Menu

### 4.5 Event Notifications
- **Red dot indicators**: Appear on relevant menu icons when new events or rewards are available
  - Paimon Menu icons (Events, Mail, Battle Pass)
  - Top-right system icons
- **Event start/end notifications**: Slide-in banners

### 4.6 Red Dot System (New Items / Unread)
- **Red dots** (small red circles) appear on:
  - Menu icons with new content
  - Character portraits with unviewed constellations
  - Inventory tabs with new items
  - Mail icon with unread mail
  - Event buttons with unclaimed rewards
- These are persistent until the player views the relevant content

---

## 5. Loading Screens

### 5.1 Visual Appearance
- **Primary loading screen**: Dark scene with a large ornate **door** in the center
  - Door gradually opens as loading progresses (visual metaphor for entering Teyvat)
  - Door is flanked by elemental symbols
  - Background shows a landscape vista
- **Area transition loading**: Similar door animation with area-specific art
- **Domain loading**: Domain-specific loading screen with tip text

### 5.2 Loading Tips
- **Tip text**: Displayed at the bottom of the loading screen
  - White text on dark background
  - Rotates through gameplay tips and lore
  - Tips are region-specific (e.g., Sumeru tips appear when loading into Sumeru)
  - Over 500 unique tips documented on the wiki

### 5.3 Loading Completion Indicator
- **No explicit progress bar or percentage** exists on the loading screen
- **Visual cues for completion**:
  - The door fully opens
  - Elemental symbols appear and stabilize
  - Screen fades to black briefly, then the game world appears
- **Known issue**: In co-op domains, there is no indicator of whether teammates have finished loading. The host can start without waiting, which is a common community complaint.

### 5.4 Boot Sequence
1. **Launcher** (if using launcher): Click "Launch" button
2. **Splash screen**: HoYoverse / miHoYo logo
3. **Door loading screen**: Door animation with loading
4. **Login screen**: Door fully open, "Click to Start" or "START GAME" button visible
5. **Game world loads**: Transition into the overworld

---

## 6. Settings Menu

### 6.1 Access
- Paimon Menu > Settings (gear icon)
- A limited version is accessible from the Login Menu (before entering the game)

### 6.2 Settings Categories (Left Sidebar)
The Settings menu uses a **left sidebar** with category tabs:

1. **Controls**
   - Control Type (Keyboard / Controller / Touchscreen)
   - Vibration (controller only)
   - Camera sensitivity sliders (horizontal, vertical, aimed shot)
   - Camera axis inversion (controller only)
   - Gyro aiming (mobile only)
   - Walk/Run toggle mode
   - Camera Y-axis auto-reset
   - Combat camera settings
   - Default camera distance (4.5 - 6.0)
   - Boat camera correction

2. **Key Bindings** (PC only)
   - Full list of remappable keybinds
   - Configure Shortcut Wheel button
   - Hard-mapped keys cannot be changed here (no UI for them)

3. **Controller Setup** (when controller is connected)
   - Face button remapping for combat (Attack, Skill, Burst, Sprint, Jump, Interact)
   - Confirm/Cancel button swap

4. **Graphics**
   - Graphics Quality preset (Lowest / Low / Medium / High / Custom)
   - Display Mode (Fullscreen / Borderless / Windowed)
   - Brightness adjustment
   - **Custom sub-settings** (when set to Custom):
     - FPS (24, 30, 45, 60, 120 on select iOS)
     - VSync (Off / On)
     - Render Resolution (0.6 - 1.5)
     - Shadow Quality (Lowest - High)
     - Global Illumination (Off / Medium / High / Extreme)
     - Visual Effects (Lowest - High)
     - SFX Quality (Lowest - High)
     - Environment Detail (Lowest - Highest)
     - Anti-Aliasing (Off / FSR2 / SMAA) [PC/Console only]
     - Volumetric Fog (Off / On)
     - Reflections (Off / On)
     - Motion Blur (Off / Low / High / Extreme)
     - Bloom (Off / On)
     - Crowd Density (Low / High)
     - Co-Op Teammate Effects (Off / Partially Off / On)
     - Subsurface Scattering (Off / Medium / High)
     - Anisotropic Filtering (1x - 16x)
     - Dynamic Character Resolution (Off / On)
   - Compatibility Mode (sets everything to minimum)
   - **NO FOV slider** exists in any version
   - **NO UI Scale slider** exists in any version

5. **Audio**
   - Master Volume (1-10)
   - Music Volume (1-10)
   - Dialogue Volume (1-10)
   - SFX Volume (1-10)
   - Dynamic Range (Full / Limited)
   - Output Settings (Stereo / Surround)
   - Mute When Minimized (PC only, Off / On)

6. **Messages** (notification toggles)
   - Resin full notification (mobile only)
   - Expedition complete notification (mobile only)

7. **Language**
   - Game Language (14 languages)
   - Voice-Over Language (Chinese, English, Japanese, Korean)
   - Manage Voice-Over Files (download/uninstall voice packs)

8. **Account**
   - User Center (opens browser)
   - Redeem Code (input field + redeem button)
   - Privacy Policy

9. **Resources**
   - Quest Resource Management (mobile only - delete old quest audio/video)
   - Verify File Integrity (starts scan, ~75 seconds on SSD)

10. **Other**
    - Mini-Map Settings (Rotating / Fixed)
    - Auto-Play Story (On / Off)
    - Auto-Lock 4-Star Weapons (On / Off)
    - Party Setup background region-based toggle
    - Allow Auto Adding 5-Star Artifacts as Enhancement Materials
    - Hide UI (On / Off) -- also toggled with `/` key on PC
    - Highlight recommended attributes on Character Artifact screen

### 6.3 Key Limitations for Vision Agents
- **No FOV slider**: Cannot programmatically change field of view
- **No UI Scale**: UI elements are always proportional to screen resolution
- **Resolution tied to display**: Game resolution matches window/monitor resolution
- **Settings are device-specific**: Stored locally (registry) + cloud synced
- **Graphics preset bugs**: v4.0+ has a known bug where switching presets shows incorrect values until you leave and re-enter the settings screen

---

## 7. Battle Pass / Events UI

### 7.1 Battle Pass Screen
- **Access**: Hotkey F4 or Paimon Menu > Battle Pass
- **Layout**: Horizontal reward track showing tiers (1-50+)
  - Free track rewards on top row
  - Paid track (Gnostic Hymn) rewards on bottom row
  - Current tier highlighted
  - **Claim buttons** appear as gold/amber rectangles on unlocked tiers
  - Uncollected rewards show a pulsing glow
- **Tabs**:
  - **BP Missions**: Daily/weekly/periodic missions with progress bars
  - **BP Rewards**: The tier track view
- **Purchase section**: Upgrade to Gnostic Hymn or Gnostic Chorus
- **Red dot** appears on Battle Pass icon when unclaimed rewards exist

### 7.2 Events Screen
- **Access**: Hotkey F5 or Paimon Menu > Events
- **Layout**: Vertical scrollable list of ongoing events
  - Each event shows: banner art, event name, duration timer, participation status
  - **"Go to Event" button** (gold rectangle) to open the event's specific screen
- **Event-specific screens** vary greatly by event type but generally share:
  - Banner/header artwork at top
  - Event description and rules
  - Participation/progression UI in center
  - **Reward preview** section
  - **Claim Reward** button (gold/amber, appears when conditions are met)
- **Web-based events**: Some event screens are rendered in an embedded browser
  - These can cause performance issues and G-Sync/VRR breaks
  - Visually distinct from native UI (web-rendered styling)

---

## 8. Wish / Gacha Screen

### 8.1 Wish Screen Layout
- **Access**: Hotkey F3 or Paimon Menu > Wish
- **Layout**:
  - **Banner carousel** (top): Horizontal swipeable banners for active wish types
    - Character Event Wish (featured 5-star character)
    - Character Event Wish-2 (second banner, since v3.0)
    - Weapon Event Wish (Epitome Invocation)
    - Standard Wish (Wanderlust Invocation)
    - Chronicled Wish (since v4.5, features rerun 5-stars)
  - **Banner art**: Large promotional artwork for the featured character/weapon
  - **Timer**: Remaining duration for limited banners (days/hours)
  - **Details button**: Opens full item pool and rates
  - **Wish buttons** (bottom area):
    - "x1 Wish" button (160 Primogems / 1 Fate)
    - "x10 Wish" button (1,600 Primogems / 10 Fates)
    - Primogem/Fate count displayed near the buttons
  - **History button**: View past wish results (last 6 months)
- **Banner types** have distinct visual styling:
  - Character banners: Feature character artwork, element-colored accents
  - Weapon banners: Feature weapon lineup, blue/purple tones
  - Standard banner: Permanent, blue-themed

### 8.2 Wish Animation
- **Single pull animation sequence**:
  1. Shooting star streaks across screen
  2. Color of meteor indicates rarity:
     - Blue streak = 3-star
     - Purple streak with gold sparkles = 4-star
     - Gold streak = 5-star
  3. Full animation plays for 4-star and 5-star results
  4. 3-star results show quickly with minimal animation
- **10-pull animation**:
  1. Ten shooting stars
  2. The highest-rarity result determines the main animation
  3. Results shown in a grid after animation
- **Skip animation**: Players CAN skip by clicking/tapping during the animation
  - No dedicated "Skip" button -- just click anywhere
  - Skipping reveals results immediately
  - A known "glitch": Brief pause before animation starts indicates gold (5-star) result
- **Result screen**: Grid of obtained items with star-rarity backgrounds

---

## 9. Key Visual Markers

### 9.1 Red Exclamation Marks
- **Purpose**: Indicates new/unviewed items or content
- **Locations where they appear**:
  - Inventory: On newly acquired weapons, artifacts, materials
  - Character screen: On new constellation nodes
  - Paimon Menu: On menu icons with new content (Events, Mail, etc.)
  - Quest log: On newly available quests
  - Adventurer Handbook: On new entries
- **Visual**: Small red circle with white "!" or simply a red dot
- **Dismissal**: Automatically removed when the relevant screen/item is viewed

### 9.2 Blue Dots on Minimap
- **Purpose**: Indicates nearby **interactable objects**
- **Objects that show as blue dots**:
  - NPCs available for interaction
  - Crafting benches (Alchemy, Blacksmith, Cooking)
  - Teleport Waypoints
  - Statue of The Seven
  - Domain entrances
  - Some quest-specific interactables
- **Not all interactables show blue dots** -- resource nodes (ores, plants) do NOT appear on minimap
- **Visual**: Small blue circle on the minimap, fades when very close

### 9.3 Yellow Markers (Quest Objectives)
- **Purpose**: Indicates active quest objectives and tracked locations
- **Visual**:
  - On minimap: Yellow diamond or circle markers
  - In 3D world: Floating yellow/gold marker beam visible at distance
  - Navigation arrow: Gold arrow in screen center pointing toward objective
  - Distance number displayed beneath the arrow
- **Quest types by marker style**:
  - Main Archon Quests: Large gold markers
  - Story Quests: Slightly different gold marker style
  - World Quests: Blue-tinted markers
  - Daily Commissions: Small markers, commission-specific icons
  - Tracked custom pins: Player-set markers (several icon/color options)

### 9.4 Chest Types - Visual Differences

| Chest Type | Visual Appearance | Primogems | Spawn Condition |
|---|---|---|---|
| **Common** | Small, plain wooden chest. Brown/dull color. Minimal glow. | 0 (most regions), 2 (some later regions) | Defeating small enemy camps, basic exploration |
| **Exquisite** | Slightly more ornate. Blue/purple tinted. Subtle glow effect. | 2 | Hidden spots, guarded by enemies |
| **Precious** | Gold-trimmed decoration. Noticeable golden glow and particle effects. | 5 | Puzzle completion, stronger enemy groups |
| **Luxurious** | Large, very ornate. Bright golden glow with prominent particles/sparkles. Red jewel decoration. | 10-40 | Major puzzles, quest rewards, hidden behind significant challenges |
| **Remarkable** | Unique appearance (varies by region). Often contains furniture blueprints. | Varies | Enkanomiya, Mirage events, Nod-Krai, specific areas |

**Chest detection cues for vision agents:**
- All chest types emit a subtle glow visible from moderate distance
- The glow intensity and particle effect scale with rarity
- Chests have a slight sparkle animation
- Common chests can be very easy to miss visually (small, low contrast)
- Luxurious chests are unmistakable (large, bright golden glow with particles)
- Some chests are hidden and only appear after solving puzzles or defeating enemies

### 9.5 Other Important Visual Markers

| Marker | Appearance | Meaning |
|---|---|---|
| **Star icon (minimap)** | Small star shape on minimap | Nearby Oculus (Anemoculus, Geoculus, etc.) |
| **White arrow** | Arrow pointing up/down | Oculus is above/below current elevation |
| **Chest icon (minimap)** | Small chest shape | Nearby treasure chest (not always visible) |
| **Enemy indicator** | Red highlight/threat marker | Enemy aggression / targeting player |
| **Elemental Sight overlay** | Blue-tinted view with highlighted outlines | Activated by holding Middle Mouse Button. Shows: element-colored outlines for interactables, grey for non-interactable, hidden paths, resource node types. |
| **Interaction F prompt** | "F" key icon with text near character | Nearby interactable object within range |
| **Loot drop beam** | Vertical colored beam | Item drop from defeated enemy or collected resource. Color indicates rarity. |

---

## 10. Resolution and Aspect Ratio

### 10.1 Supported Resolutions and Aspect Ratios

| Resolution | Aspect Ratio | Support Level | Notes |
|---|---|---|---|
| 1280x720 (720p) | 16:9 | Full | Minimum common resolution |
| 1920x1080 (1080p) | 16:9 | Full | **Recommended for vision agents** |
| 2560x1440 (1440p) | 16:9 | Full | High quality, UI scales proportionally |
| 3840x2160 (4K) | 16:9 | Full | UI may appear small without UI scale option |
| 2560x1080 | 21:9 | Full | Ultrawide, works well |
| 3440x1440 | 21:9 | Full | Ultrawide, works well, some cutscene framing issues |
| 5120x1440 | 32:9 | Full | Super ultrawide, supported but rare |
| 1920x1200 | 16:10 | Partial | Renders at original ratio, may stretch or letterbox |

### 10.2 UI Scaling Behavior
- **UI elements scale proportionally with resolution**
  - At 1920x1080: Standard element sizes
  - At 2560x1440: Same proportions, higher pixel density
  - At 3840x2160: Same proportions, even higher density (elements may look small on same physical monitor)
- **No independent UI scale slider exists** in any version of the game
- **UI is anchored to screen edges** with no dead-zone centering option
- **Ultrawide**: UI elements remain at edges (not centered to 16:9 area), giving more horizontal game world visibility

### 10.3 Recommendation for Vision Agents
```
Display Mode: Borderless Windowed (for reliable screen capture)
Resolution: 1920x1080 (standard, best for template matching / OCR consistency)
Render Resolution: 1.0 (no upscaling artifacts)
FPS: 60
VSync: Off
```
- 1920x1080 is the ideal resolution because:
  - Most template matching / OCR tools are tuned for this resolution
  - Most community resources and screenshots use 1080p
  - Fastest capture processing time
  - Consistent across different hardware configurations
  - Existing Genshin automation bots (e.g., BOT-MMORPG-AI) target this resolution

---

## 11. Screen State Classification Guide

For a vision agent that needs to classify "what screen am I looking at", here are the key discriminators:

| Screen State | Key Visual Markers | Detection Method |
|---|---|---|
| **Overworld (HUD visible)** | Minimap (top-left), HP bar (bottom-center), skill buttons (bottom-right), party portraits (right) | Template match minimap circle + skill button area |
| **Overworld (HUD hidden)** | No UI elements, clean game world view | Absence of minimap + HP bar templates |
| **Paimon Menu** | Dimmed background, grid of menu icons, Paimon character visible | Template match Paimon or menu grid pattern |
| **Map (full screen)** | Large map with region names, waypoint icons, zoom controls | Template match map border or compass rose |
| **Inventory** | Item grid with rarity-colored backgrounds, left sidebar tabs | Template match inventory tab icons or item grid pattern |
| **Character Screen** | 3D character model, left sidebar with attribute/weapon/artifact tabs | Template match character screen tab bar |
| **Party Setup** | 4 character slots, character select grid | Template match party slot frames |
| **Dialog / Conversation** | Semi-transparent dialog box (bottom 25-30%), NPC portrait, text | Template match dialog box background or portrait frame |
| **Dialog with Choices** | Same as dialog + 2-4 choice buttons above dialog box | Detect choice button rectangles |
| **Loading Screen** | Door animation, dark background, tip text at bottom | Template match door frame or detect dark screen + tip text |
| **Login Screen** | "START GAME" / "Click to Start" button, door fully open | Template match START GAME button |
| **Wish Screen** | Banner artwork, wish buttons (x1, x10), Primogem count | Template match wish button area |
| **Battle Pass** | Horizontal tier track, BP level indicator, mission tabs | Template match BP tier track |
| **Events Screen** | Event list with banner thumbnails, "Go to Event" buttons | Template match event entry pattern |
| **Domain / Combat** | Challenge timer (top-center), enemy HP bars, domain-specific UI | Template match timer display |
| **Crafting / Cooking** | Ingredient slots, recipe list, craft/forge button | Template match crafting bench area |
| **Cutscene** | Cinematic letterboxing (black bars top/bottom), no HUD | Detect letterbox bars + absence of HUD |
| **Adventurer Handbook** | Book-style interface, chapter tabs, task list | Template match handbook tab icons |

### 11.1 Reliable Detection Anchors (Resolution-Independent)

These UI elements are highly consistent across versions and can serve as reliable anchors:

1. **Minimap circle** (top-left): Always circular, always in top-left corner during overworld
2. **HP bar** (bottom-center): Always green/yellow/red horizontal bar during overworld
3. **Skill button area** (bottom-right): Always has E/Q icons with element colors
4. **Dialog box** (bottom-center): Always semi-transparent panel with text
5. **Loading door**: Always present during loading screens
6. **Paimon character**: Always appears on Paimon Menu

### 11.2 Detection Priority Order
When classifying screen state, check in this order for fastest determination:
1. **Loading screen** (dark + door) -- most critical to detect for agent timing
2. **Dialog box** (bottom panel) -- prevents accidental actions during conversations
3. **Paimon Menu** (menu overlay) -- prevents accidental key presses
4. **Full-screen overlay menus** (Map, Inventory, Character, etc.)
5. **Overworld HUD** (minimap + HP bar) -- default gameplay state
6. **Overworld no HUD** -- photo mode or HUD hidden

---

## 12. Additional Visual Elements

### 12.1 Elemental Colors (for vision detection)
| Element | Primary Color | Hex (approximate) |
|---|---|---|
| Pyro (Fire) | Orange-Red | #FF6B35 |
| Hydro (Water) | Blue | #4CC2F1 |
| Electro (Lightning) | Purple | #B07FD0 |
| Cryo (Ice) | Light Blue | #9FD6E6 |
| Anemo (Wind) | Teal-Green | #74C2A8 |
| Geo (Earth) | Amber-Gold | #F0B323 |
| Dendro (Nature) | Green | #A5C83B |

### 12.2 Rarity Colors (for item/loot detection)
| Rarity | Background Color | Border |
|---|---|---|
| 1-Star | Grey | Thin grey |
| 2-Star | Green | Green border |
| 3-Star | Blue | Blue border |
| 4-Star | Purple | Purple border, subtle glow |
| 5-Star | Gold | Gold border, prominent glow/sparkle |

### 12.3 Common Button Styles
- **Primary action button**: Gold/amber rectangle with rounded corners, white text, subtle gradient
- **Secondary button**: Dark semi-transparent rectangle with lighter border
- **Cancel button**: Grey or dark-toned rectangle
- **Tab (active)**: Bright element with bottom border highlight
- **Tab (inactive)**: Dimmed, grey text
- **Toggle (on)**: Filled, bright color
- **Toggle (off)**: Empty, dark/grey

---

## Sources

- [Game UI Database - Genshin Impact](https://www.gameuidatabase.com/gameData.php?id=470)
- [Genshin Impact Wiki (Fandom) - Settings](https://genshin-impact.fandom.com/wiki/Settings)
- [Genshin Impact Wiki (Fandom) - Map](https://genshin-impact.fandom.com/wiki/Map)
- [Genshin Impact Wiki (Fandom) - Chest](https://genshin-impact.fandom.com/wiki/Chest)
- [Genshin Impact Wiki (Fandom) - Party](https://genshin-impact.fandom.com/wiki/Party)
- [Genshin Impact Wiki (Fandom) - Controls](https://genshin-impact.fandom.com/wiki/Controls)
- [Genshin Impact Wiki (Fandom) - Loading Screen](https://genshin-impact.fandom.com/wiki/Loading_Screen/Others)
- [Genshin Impact Wiki (Fandom) - Wish](https://genshin-impact.fandom.com/wiki/Wish)
- [Genshin Impact Wiki (Fandom) - Adventurer Handbook](https://genshin-impact.fandom.com/wiki/Adventurer_Handbook)
- [Interface In Game - Genshin Impact Mobile](https://interfaceingame.com/games/genshin-impact-mobile/)
- [PCGamingWiki - Genshin Impact](https://www.pcgamingwiki.com/wiki/Genshin_Impact)
- [HoYoLAB - Starter Guide UI Explanation](https://www.hoyolab.com/article/5921298)
- [HoYoLAB - Graphics Settings Guide](https://www.hoyolab.com/article/1418398)
- [HoYoLAB - Paimon Menu Key Guide](https://www.hoyolab.com/article/4628362)
- [HardReset - Character Menu Layout](https://www.hardreset.info/devices/apps/apps-genshin-impact/open-characters-menu/)
- [GameFAQs - Icons Around Minimap](https://gamefaqs.gamespot.com/boards/270518-genshin-impact/79370979)
- [Gaming StackExchange - Star Icon on Minimap](https://gaming.stackexchange.com/questions/376279/what-does-this-star-icon-mean-on-genshin-impacts-minimap)
- [Pocket Tactics - Genshin Impact Icons Guide](https://www.pockettactics.com/genshin-impact/icons)
- [Reddit - Loading Indicator Discussion](https://www.reddit.com/r/Genshin_Impact/comments/18amk2y/i_wish_genshin_have_loading_indicator_so_people/)
- [Reddit - Skip Dialogue Discussion](https://www.reddit.com/r/Genshin_Impact/comments/1hxfp0f/for_the_love_of_god_let_us_skip_dialogue/)
- [HoYoLAB - New Dialogue UI Buttons](https://www.hoyolab.com/article/29099487)
- [HoYoVERSe Official - Mini-Map Marker Component Tutorial](https://act.hoyoverse.com/ys/ugc/tutorial/detail/mh0pppib5eyc)
- [GitHub - Genshin Impact Wish Simulator](https://github.com/jaihysc/Genshin-Impact-Wish-Simulator)
- [GitHub - BOT-MMORPG-AI](https://github.com/ruslanmv/BOT-MMORPG-AI)
- [GitHub - genshingrab (HUD Scraper)](https://github.com/maufirf/genshingrab)
- [GitHub - Inventory Kamera (OCR Scanner)](https://github.com/Andrewthe13th/Inventory_Kamera)
- [Medium - Automating Genshin Impact with Python](https://medium.com/@coderhack.com/automating-genshin-impact-with-python-127c7cebc671)
- [HoYoLAB - Skip Wish Animation](https://www.hoyolab.com/article/187166)
- [Behance - Genshin Wish Banner Redesign](https://www.behance.net/gallery/165263905/Genshin-Impacts-Wish-Banner-Redesign)
- [Game8 - Party Setup Background Guide](https://game8.co/games/Genshin-Impact/archives/420275)
- [HoYoLAB - Primogems from Chests](https://www.hoyolab.com/article/199177)
