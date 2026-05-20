# Genshin Impact (原神) Technical Specifications for Vision Agent Development

**Research Date:** 2026-05-20  
**Game Version at Research:** ~5.x / 6.x era  

---

## 1. PC Version Technical Specs

### Executable / Process

| Property | Global Version | Chinese Version |
|---|---|---|
| **Executable Name** | `GenshinImpact.exe` | `YuanShen.exe` |
| **Window Title** | `Genshin Impact` | `原神` |
| **Architecture** | 64-bit | 64-bit |
| **Publisher** | HoYoverse / Cognosphere | miHoYo (China) |

**Installation Path (typical):**
```
<drive>:\Genshin Impact\Genshin Impact Game\GenshinImpact.exe
```

**Launch parameters of interest:**
- `-popupwindow -screen-height 1080 -screen-width 1920` -- borderless windowed mode
- `-screen-fullscreen 1 -window-mode exclusive` -- exclusive fullscreen (fixes G-Sync stutter)
- `use_mobile_platform -is_cloud 1 -platform_type CLOUD_THIRD_PARTY_MOBILE` -- mobile UI mode (touch-optimized, no standard KB/M input)

### Engine & Graphics

| Property | Value |
|---|---|
| **Engine** | Unity 2017 (build 2017.4.30f1) |
| **Graphics API** | Direct3D 11 |
| **Middleware (Audio)** | Wwise |
| **Middleware (Input)** | Rewired |
| **Anti-Cheat** | HoYoKProtect (`mhyprot2.sys` / `HoYoKProtect.sys`) |

### Supported Resolutions

- Standard widescreen resolutions supported (720p through 4K)
- **Render Resolution** is adjustable (0.8x to 1.5x native)
- Ultra-wide (21:9, 31:9) supported but UI is anchored to full screen with no dead-zone centering
- Multi-monitor works (unverified edge cases)
- 4K Ultra HD supported

### Display Modes

| Mode | Availability | Notes |
|---|---|---|
| **Exclusive Fullscreen** | Yes | Default. Minimizes on Alt+Tab. Required for G-Sync/VRR to work properly. |
| **Windowed** | Yes | In-game setting under Settings > Graphics. |
| **Borderless Windowed** | Yes (since v4.4) | Available as an in-game graphics option. Previously required `-popupwindow` launch parameter or Alt+Enter toggle. |
| **Alt+Enter** | Yes | Toggles between fullscreen and windowed/borderless. |

**IMPORTANT for screen capture agents:** Borderless windowed mode is strongly recommended because:
- It does not minimize on focus loss (unlike exclusive fullscreen)
- Screen capture tools (OBS, Python mss/pyautogui) work reliably
- Alt+Tab is seamless
- The `Mute When Minimized` setting (added v4.1) works differently in borderless: audio continues even when unfocused

### Screen Capture Compatibility

- **OBS Game Capture:** Works but requires enabling "anti-cheat compatibility hooking" in OBS Game Capture properties
- **OBS Window/Display Capture:** Works in windowed/borderless mode
- **Common issue:** Black screen capture occurs if OBS and game are running on different GPUs. Fix: force both to use same GPU via Windows Graphics Settings
- **Python libraries (mss, PIL, pyautogui, dxcam):** Should work in windowed/borderless mode. Desktop Duplication API may have issues with exclusive fullscreen due to D3D exclusive mode

### Registry Location

```
HKEY_CURRENT_USER\SOFTWARE\miHoYo\Genshin Impact
```
- Key `WINDOWS_HDR_ON_h3132281285` (DWORD) -- HDR toggle
- Most game settings stored here
- Not easily editable for keybindings (cloud-synced)

### Log File Location

```
%USERPROFILE%\AppData\LocalLow\miHoYo\Genshin Impact\output_log.txt
```

### System Requirements (as of Version 6.0)

| | Minimum | Recommended |
|---|---|---|
| **OS** | Windows 10 64-bit | Windows 11 64-bit |
| **CPU** | Intel Core i5 6th Gen / AMD Ryzen | Intel Core i7 7th Gen / AMD Ryzen 5000 |
| **RAM** | 8 GB | 16 GB |
| **Storage** | 110 GB (HDD) | 150 GB (SSD) |
| **GPU** | GeForce GT 1050 / Intel Iris Xe / DX11 compatible | GeForce GTX 1060 6GB VRAM |

**Constant internet connection required for all game modes.**

---

## 2. Input System

### Complete Default PC Keybindings

#### Movement & Camera
| Action | Default Key | Remappable? |
|---|---|---|
| Move Forward | `W` | Yes |
| Move Backward | `S` | Yes |
| Move Left | `A` | Yes |
| Move Right | `D` | Yes |
| Rotate Camera | `Mouse` (move) | N/A |
| Jump / Move Up | `Space` | Yes |
| Walk/Run Toggle / Crouch | `Left Ctrl` | Yes |
| Sprint | `Left Shift` (hold) | Yes |
| Sprint (alt) | `Right Click` (hold) | **NO** (hard-mapped) |
| Drop (while climbing) | `X` | Yes |

#### Combat
| Action | Default Key | Remappable? |
|---|---|---|
| Normal Attack | `Left Click` | **NO** (hard-mapped) |
| Elemental Skill | `E` | Yes |
| Elemental Burst | `Q` | Yes |
| Switch Aiming Mode (Bow) | `R` | Yes |
| Switch to Party Member 1 | `1` | Yes |
| Switch to Party Member 2 | `2` | Yes |
| Switch to Party Member 3 | `3` | Yes |
| Switch to Party Member 4 | `4` | Yes |
| Switch to Party Member 5 | `5` | Yes |
| Switch + Use Burst (Member N) | `Left Alt` + `N` | **NO** (hard-mapped) |
| Quick-Use Gadget | `Z` | Yes |
| Gadget Quickswap | Hold `Z` | Yes |
| Interaction in Gameplay Modes | `T` | Yes |
| Quest Navigation | `V` | Yes |
| Show Objective Details | Hold `V` | Yes |
| Abandon Challenge | `P` | Yes |

#### Interact & Pickup
| Action | Default Key | Remappable? |
|---|---|---|
| Pick Up / Interact | `F` | Yes |
| Elemental Sight (Hold) | `Middle Click` | **NO** (hard-mapped) |
| Reset Camera Angle | `Middle Click` | **NO** (same as Elemental Sight) |

#### Menus
| Action | Default Key | Remappable? |
|---|---|---|
| Paimon Menu (Main Menu) | `Esc` | **NO** (hard-mapped) |
| Open Shortcut Wheel | `Tab` | Yes |
| Open Inventory (Bag) | `B` | Yes |
| Open Character Screen | `C` | Yes |
| Open Map | `M` | Yes |
| Open Quest Menu | `J` | Yes |
| Open Adventurer Handbook | `F1` | Yes |
| Open Co-Op Screen | `F2` | Yes |
| Open Wish Screen | `F3` | Yes |
| Open Battle Pass | `F4` | Yes |
| Open Events Menu | `F5` | Yes |
| Open Serenitea Pot Settings | `F6` | Yes |
| Open Furnishing Screen | `F7` | Yes |
| Open Stellar Reunion | `F8` | Yes |
| Open Party Setup | `L` | Yes |
| Open Friends Screen | `O` | Yes |
| Open Chat | `Enter` | Yes |
| Open Notification Details | `Y` | Yes |
| Open Special Env. Info | `U` | Yes |
| Check Tutorial Details | `G` | Yes |
| Show Cursor | `Left Alt` (hold) | **NO** (hard-mapped) |
| Hide Main Menu | `\` (backslash) | Yes |

#### Photo Mode (separate keybinds)
| Action | Default Key |
|---|---|
| Picture Settings | `F1` |
| Character Pose | `F2` |
| Character Expression | `F3` |
| Hide UI | `Ctrl` + `H` |
| Take Photo | `Enter` |

### Keybinding Remapping

- **Available since Version 1.1** (in-game: Settings > Controls > Key Bindings)
- **Hard-mapped keys that CANNOT be changed:**
  - Left Click = Normal Attack
  - Right Click = Sprint (hold) / Aim (bow)
  - Middle Click = Elemental Sight / Reset Camera
  - Esc = Paimon Menu
  - Left Alt (hold) = Show Cursor
  - Left Alt + 1/2/3/4 = Switch and use Burst
- **Settings are stored:** Windows Registry + server-side cloud sync (no editable config file)
- **Registry path:** `HKEY_CURRENT_USER\SOFTWARE\miHoYo\Genshin Impact`
- Settings carry over between PCs via HoYoverse account

### Mouse Sensitivity

| Setting | Details |
|---|---|
| **Camera Sensitivity** | Slider 1-10 (separate for normal and aimed shot) |
| **Vertical vs Horizontal** | Vertical is 75% lower than horizontal (50% in Aimed Shot). NOT adjustable. |
| **Mouse Acceleration** | Force-enabled (mouse smoothing). Cannot be disabled in-game. |
| **Resolution Scaling Bug** | Sensitivity at a given slider value decreases as resolution increases. x1.0 at 1080p = x0.5 at 2160p. Workaround: set to 1080p, adjust slider, change back to 2160p. Must redo after each restart. |
| **Raw Input** | NOT supported |

**IMPORTANT for agents:** The forced mouse smoothing and asymmetric X/Y sensitivity make pixel-precise mouse control unreliable. For a vision agent:
- Prefer keyboard movement (WASD) over mouse navigation
- Mouse-based camera rotation will have acceleration/smoothing artifacts
- Consider pre-calibrated sensitivity offsets if using mouse for camera control

### Controller Support

| Controller Type | Support Level |
|---|---|
| **Xbox (XInput)** | Native, plug-and-play |
| **PlayStation (DualShock 4 / DualSense)** | Native since v2.2. Must be connected before game start for DualSense. |
| **Switch Pro** | Partial (detected but may not work fully) |
| **DirectInput (generic)** | Supported |
| **Touch (PC)** | NOT supported (mobile only) |

- Switching to Controller mode changes UI to "Console mode" (larger fonts, button prompts)
- Controller remapping: only face buttons and right shoulder buttons can be remapped
- Controller camera sensitivity: separate sliders, vertical is 50% of horizontal
- Y-axis inversion available on controller (not on KB/M)
- DualSense touchpad used for co-op text chat

---

## 3. Anti-Cheat System

### Overview

| Property | Details |
|---|---|
| **Anti-Cheat Name** | `mhyprot2.sys` / `HoYoKProtect.sys` |
| **Type** | Kernel-level (Ring 0) driver |
| **Developer** | miHoYo / HoYoverse (proprietary, in-house) |
| **Active When** | Only while the game is running |
| **After Game Closes** | Driver stops; no background monitoring |
| **Known CVE** | CVE-2020-36603 (insufficient restriction of unprivileged function calls) |

### What It Monitors (Public Knowledge)

The anti-cheat driver operates at kernel level and is known to:
- Monitor system memory and processes for known cheat software
- Detect game memory modification / injection
- Scan for unauthorized DLL injection into the game process
- Remove extraneous DLLs from the game directory on startup

### What Is Detectable

| Category | Detectability | Risk Level |
|---|---|---|
| **Game memory modification** | Detected | HIGH -- bannable |
| **DLL injection into game process** | Detected | HIGH -- bannable |
| **Speed hacks / teleport hacks** | Detected | HIGH -- bannable |
| **Third-party tools modifying game memory** | Detected (even FPS unlockers) | MEDIUM -- ToS violation, but historically unenforced for FPS unlocker |
| **Screen reading / OCR** | NOT detected | LOW -- no code injection |
| **Pixel-based image detection** | NOT detected | LOW -- operates at OS level, not game level |
| **Keyboard/mouse macros (external)** | Low risk | LOW-MEDIUM -- considered "auxiliary" by anti-cheat, not injection |
| **OBS / screen recording** | NOT flagged | LOW -- widely used by streamers |
| **Discord / Razer Cortex** | Rarely flagged | LOW -- occasional false positives reported |

### Screen Capture Tool Compatibility

- **OBS:** Works. Enable "anti-cheat compatibility hooking" in Game Capture properties to avoid black screen.
- **Windows Game Bar:** Works.
- **Python mss / PIL / pyautogui:** Should work (read-only screen capture, no game interaction).
- **dxcam / Desktop Duplication API:** May have issues in exclusive fullscreen; use borderless windowed mode.

### Safety Guidance for Vision Agent Development

1. **Screen reading (pixel capture / OCR) is the safest approach** -- it does not interact with game memory
2. **Input simulation via OS-level APIs (SendInput, pyautogui)** is external to the game and not detectable by kernel-level anti-cheat
3. **NEVER** inject code into the game process or modify game memory
4. **NEVER** modify game files
5. The FPS unlocker community tool has existed for 4+ years without bans, suggesting external non-injection tools are tolerated, but this is not guaranteed
6. Some users have reported false-positive bans from running background apps (Discord, Razer Cortex) -- extremely rare but documented

**DISCLAIMER:** This document contains only publicly available information. No exploit details, bypass methods, or reverse-engineering instructions are included. Using any third-party tool with Genshin Impact may violate the Terms of Service.

---

## 4. Performance / Frame Rate

### Frame Rate Settings

| Setting | Value |
|---|---|
| **In-game FPS options** | 30, 45, 60 FPS |
| **Hard cap** | 60 FPS (default max) |
| **Uncapped FPS** | Possible via third-party FPS unlocker (ToS gray area) |
| **VSync** | Available (toggle in settings) |
| **FSR 2** | Supported (upscaling) |
| **HDR** | Supported (requires registry key set before each launch) |

### Typical Performance

- **60 FPS** on recommended hardware with medium-high settings
- **Frame drops** can occur during heavy particle effects, dense enemy encounters, and world transitions
- **Stuttering** is a known issue, especially when not using exclusive fullscreen or when certain background apps (Corsair iCUE) are running

### Loading Times (by Storage Type)

| Storage | Boot to Login | Teleport | Domain Entry |
|---|---|---|---|
| **HDD** | 60-120+ seconds | 30-60 seconds | 30-60 seconds |
| **SATA SSD** | 15-30 seconds | 5-15 seconds | 5-15 seconds |
| **NVMe M.2 SSD** | 5-10 seconds | 2-5 seconds | 2-5 seconds |

**Loading triggers:**
- Initial game launch -> door loading screen
- Teleporting (waypoints, statues)
- Entering/exiting domains (dungeons)
- Cutscene transitions
- First load after game update (longer due to asset pre-rendering)

**IMPORTANT for agents:** Loading screen detection is critical. The game shows a distinct loading screen with a door animation and lore text during all transitions. The agent must wait for loading to complete before attempting actions. On SSD, 2-5 second loads are typical for teleporting.

### Frame Timing Patterns

- Stable 60 FPS during normal gameplay
- Momentary drops during:
  - Elemental burst animations (cutscene-like camera moves)
  - Large enemy spawns
  - Weather transitions
  - Opening certain menus (especially web-based ones: Notices, Events, Wish History)
- Web-based menus can break G-Sync/VRR, requiring Alt+Tab to refocus

---

## 5. Game Version Updates

### Update Cadence

| Property | Details |
|---|---|
| **Cycle** | 6 weeks (42 days) per version |
| **Maintenance** | Typically Tuesday night/Wednesday morning |
| **Livestream** | ~10-12 days before each version launch |
| **Phase split** | Each version has two 3-week banner phases |
| **Download size** | Typically 5-15 GB per version (cumulative updates much larger) |

### Version Naming Convention

- Format: `X.Y` (e.g., 3.0, 3.1, 3.2, ... 5.0, 5.1, 5.2, ...)
- **Major versions** (X.0): New region releases (e.g., 3.0 = Sumeru, 4.0 = Fontaine, 5.0 = Natlan, 6.0 = next region)
- **Minor versions** (X.Y): Sequential content additions within a region
- **Codenames:** Each version has a subtitle (e.g., 6.4 = "Luna V", 6.6 = "Luna VII")
- **Occasional skips:** e.g., no version 6.8 was released, jumping to next major version

### Impact on UI / Screen Layout for Vision Agents

| Change Type | Frequency | Impact on Vision Agent |
|---|---|---|
| **Main menu redesign** | Major versions (X.0) | HIGH -- button positions, icon layout change significantly |
| **Settings menu reorganization** | Major versions | MEDIUM -- settings categories shift |
| **HUD element repositioning** | Rare | HIGH -- health bars, minimap, ability icons |
| **New UI screens** | Most versions | LOW -- new menus added but existing ones largely unchanged |
| **Hotkey additions** | Occasional | LOW -- new functions get new keybinds |
| **Icon/graphic updates** | Occasionally | MEDIUM -- visual appearance of buttons may change |
| **Character screen / artifact filtering** | Occasionally | MEDIUM -- layout changes in inventory screens |

**Notable UI changes by version:**
- v1.0: Initial UI
- v3.0: Redesigned main menu layout
- v4.0: Significant main menu UI overhaul, new underwater UI
- v4.4: Added native borderless windowed option, updated character screen
- v5.0: Major menu redesign (minimalist main menu, new Party Setup, revamped Settings)

**Mitigation for vision agents:**
- Use template matching with version-agnostic features (health bar color, element icons)
- Build UI element detection with tolerance for position shifts
- Version-check the game to adapt OCR/screen layout templates per version
- Pin to specific versions for development/testing

---

## 6. Co-Op / Multiplayer UI

### Unlock Condition
- Adventure Rank 16 + completion of Archon Quest Prologue Act I

### Party Structure

| Players in Co-Op | Characters per Player |
|---|---|
| 2 players | 2 characters each, can swap |
| 3 players | Host: 2 characters, Guests: 1 each |
| 4 players | 1 character each |

### Visual / UI Differences (Solo vs Co-Op)

| Element | Solo Mode | Co-Op Mode |
|---|---|---|
| **Party display** | 4 character portraits bottom-right | 4 player portraits with names + their character |
| **Character switching** | Full 4-character swap | Limited by player count (see above) |
| **Minimap** | Single player dot | Colored dots for each teammate (blue/green numbered icons) |
| **Teammate indicators** | N/A | Teammate HP bars visible, elemental indicators shown |
| **Team effects** | Own party only | Other players' elemental effects visible (can be toggled off) |
| **Chat** | Available | Party chat set as default (since v2.7) |
| **Chests** | Can open all | Only host can open chests |
| **NPCs** | Can interact | Guests cannot interact with most NPCs |
| **Quests** | All available | Story quests disabled; some quests block co-op entirely |
| **Domains** | Solo entry | Host must initiate; unique characters required |
| **Paimon Menu** | Full access | Guests have limited menu options |
| **Serenitea Pot** | Full access | Guests need friend status to enter |

### Host vs Guest Permissions

| Action | Host | Guest |
|---|---|---|
| Open chests | Yes | No |
| Activate elemental monuments | Yes | No |
| Collect Oculi | Yes | No |
| Initiate domains | Yes | No |
| Talk to NPCs | Yes (limited in co-op) | No |
| Collect enemy drops | Yes | Yes |
| Mine ores | Yes | Yes |
| Fish | Yes | Yes |
| Use healing statues | Yes | Yes (heal only) |
| Adjust time of day | No (co-op restriction) | No |
| Pause game | No | No |

### Co-Op Enemy Scaling

| Players | Enemy HP | Enemy ATK |
|---|---|---|
| 1 | 100% | 100% |
| 2 | 150% | 100% |
| 3 | 200% | 100% |
| 4 | 250% | 100% |

### Visual Agent Implications

- In co-op, the HUD shows additional teammate info (portraits, HP, names)
- Character portraits in bottom-right are replaced by player portraits
- Minimap has additional colored dots
- Teammate visual effects (elemental skills/bursts) can clutter the screen
- Cross-play between PC, Mobile, PS, Xbox is supported on same regional server

---

## Appendix A: Quick Reference for Vision Agent Development

### Recommended Display Settings for Screen Capture

```
Display Mode: Borderless Windowed (since v4.4, native option)
Resolution: 1920x1080 (standard, consistent OCR)
Render Resolution: 1.0
FPS: 60
VSync: Off (for consistent frame timing)
```

### Critical UI Elements to Detect (Screen Regions)

These are approximate positions at 1080p and may vary by version:

| Element | Screen Region | Color/Shape |
|---|---|---|
| HP bar (active char) | Bottom-center | Red/green horizontal bar |
| Character portraits | Bottom-right | Circular portraits |
| Elemental skill/burst icons | Bottom-right | E/Q key labels visible |
| Minimap | Top-right | Circular map with cardinal directions |
| Quest tracker | Top-right (below minimap) | Text overlay |
| Dialogue box | Bottom-center | Semi-transparent panel |
| Interaction prompt (F) | Center-bottom | "F" key icon + text |
| Loading screen | Full screen | Door animation + tip text |
| Paimon menu | Full screen overlay | Grid of menu icons |
| Co-op teammate list | Right side | Player name + character portrait |

### Key Timing Constants (Approximate)

| Event | Duration |
|---|---|
| Loading screen (SSD, teleport) | 2-5 seconds |
| Loading screen (SSD, domain) | 2-5 seconds |
| Loading screen (SSD, boot) | 5-10 seconds |
| Elemental burst animation | 2-4 seconds |
| Normal attack combo (4 hits) | ~2.5 seconds |
| Sprint stamina drain (full to empty) | ~6 seconds |
| Climbing stamina drain (full to empty) | ~10 seconds |
| Gliding stamina drain (full to empty) | ~40 seconds |
| Skill cooldown (typical) | 6-15 seconds |
| Burst animation lock | 1-3 seconds |

### Input Simulation Considerations

1. **Use borderless windowed mode** to avoid focus/minimize issues
2. **Prefer keyboard input over mouse** due to forced mouse smoothing
3. **Mouse camera control** will have acceleration artifacts -- calibrate empirically
4. **Key delay recommendations:** 50ms minimum between key events, 100ms for menu interactions
5. **Interact key (F)** has a cooldown of ~0.5 seconds between pickups
6. **Character switching** has ~0.5 second animation lock

---

## Sources

- [PCGamingWiki - Genshin Impact](https://www.pcgamingwiki.com/wiki/Genshin_Impact)
- [Genshin Impact Wiki (Fandom) - Controls](https://genshin-impact.fandom.com/wiki/Controls)
- [Genshin Impact Wiki (Fandom) - Co-Op Mode](https://genshin-impact.fandom.com/wiki/Co-Op_Mode)
- [Genshin Impact Wiki (Fandom) - Version](https://genshin-impact.fandom.com/wiki/Version)
- [HoYoLAB Official Anti-Cheat Statement](https://www.hoyolab.com/article/19131)
- [HoYoLAB - Key Guide for PC Players](https://www.hoyolab.com/article/4628362)
- [Game8 - Controls Guide](https://game8.co/games/Genshin-Impact/archives/297508)
- [DefKey - Genshin Impact Keyboard Shortcuts](https://defkey.com/genshin-impact-shortcuts)
- [Gaming StackExchange - Borderless Windowed Mode](https://gaming.stackexchange.com/questions/376527/how-can-you-run-genshin-impact-in-borderless-windowed-mode)
- [Reddit - OBS Black Screen Fix](https://www.reddit.com/r/obs/comments/j1fiia/trying_to_capture_genshin_impact_gets_black/)
- [Trend Micro - mhyprot2 Ransomware Abuse](https://www.trendmicro.com/en_us/research/22/h/ransomware-actor-abuses-genshin-impact-anti-cheat-driver-to-kill-antivirus.html)
- [NVD - CVE-2020-36603](https://nvd.nist.gov/vuln/detail/CVE-2020-36603)
- [Zhihu - Image Detection & Macros](https://www.zhihu.com/en/answer/3315271926)
- [HoYoLAB - Device Performance Requirements](https://www.hoyolab.com/article/40408846)
- [GitHub - Genshin FPS Unlocker](https://github.com/34736384/genshin-fps-unlock/issues/80)
