# Long-Range Vision Pipeline & Execution Safety Audit

**Scope:** Vision provider stack (llm/), execution layer (execution/), safety
boundaries, profile management.
**Session duration assumption:** 30+ minutes continuous operation.
**Auditor:** automated adversarial review.
**Date:** 2026-05-28

---

## Finding: No Failover Path When Gemma Backend Goes Down Mid-Session
(SEVERITY: CRITICAL)

**What is wrong:**
`OpenAICompatibleGemmaVisionBackend.extract_facts()` calls
`self.provider.describe_image()` which raises `ProviderRequestError` on any
HTTP failure. The caller in `extract_facts` does **not** catch this exception.
Similarly, `classify_screen`, `ground_ui`, and `explain_failure_with_image` in
`OpenAICompatibleLocalVisionProvider` all raise `ProviderRequestError` on
failure with no fallback.

`configs/model.yaml` declares `fallback_backend: deterministic` but no code
anywhere reads or acts on this key. There is no failover logic in
`OpenAICompatibleGemmaVisionBackend`, `OpenAICompatibleLocalVisionProvider`, or
`ModelRoutePolicy`.

**Why it matters for long sessions:**
A 30-minute session will see transient network errors, LM Studio restarts, GPU
OOM, or the VLM process crashing. Every single failure propagates as an
unhandled exception. The control loop receives no observation, no screen state,
and no graceful degradation. The agent either crashes or enters an
uninitialized state.

**Concrete scenario:**
LM Studio runs out of VRAM at minute 17. `urllib.request.urlopen` raises
`URLError`. `OpenAICompatibleLocalVisionProvider._chat()` wraps it as
`ProviderRequestError`. Nobody catches it. The perception plane crashes. The
StateBus receives no new observation. The deadman timer eventually fires, but
the agent has already been in an uncontrolled state for seconds.

**Suggested fix:**
- Implement a `FallbackVisionBackend` wrapper that holds a primary and fallback
  `VisionBackend`. On `ProviderRequestError`/`ProviderUnavailable`, it falls
  back to the deterministic backend.
- Read `fallback_backend` from `model.yaml` and wire it in `ModelManager` or
  the app bootstrap.
- Return a `VisionFactBundle` with `uncertainty=1.0` and `screen_state="unknown"`
  on fallback so downstream systems can adapt rather than crash.

---

## Finding: Vision Output Guard Can Be Bypassed by Subtly Malformed VLM Output
(SEVERITY: HIGH)

**What is wrong:**
The `VisionOutputGuard._contains_action_directive()` check uses a static
blocklist (`_BLOCKED_TERMS`) of English and Chinese action words. An adversarial
or drifting VLM can trivially bypass this by:
1. Using synonyms not in the list (e.g., "tap", "hit", "trigger", "activate",
   "run command", "invoke").
2. Embedding action directives in Unicode variants or zero-width characters.
3. Returning numeric pixel coordinates without the detected patterns
   `(\d{2,5},\d{2,5})` or `x=\d{2,5} y=\d{2,5}` -- e.g., using
   `"position": [847, 392]` which passes the guard untouched.

Additionally, `_parse_fact_bundle` in `gemma_vision_provider.py` only runs
`validate_candidate` for `fact_type == "ui_grounding"`. Facts of type
`screen_state`, `ocr_text_hint`, `map_marker_hypothesis`, and `dialogue_region`
skip the grounding validation entirely. A VLM could inject action directives
through any non-grounding fact type.

**Why it matters for long sessions:**
Over 30 minutes, VLM outputs can drift due to context window accumulation,
temperature fluctuations, or model warm-up effects. A VLM that starts returning
subtly directive content in `ocr_text_hint` facts would bypass the guard
entirely and inject instructions into downstream planning.

**Concrete scenario:**
The VLM returns `{"fact_type": "ocr_text_hint", "value": "press F to interact"}`
in 40% of frames. This passes validation because `fact_type != "ui_grounding"`
skips the candidate check. The value text propagates to planning, where it
could be interpreted as an instruction.

**Suggested fix:**
- Apply `_contains_action_directive` to ALL fact types, not just
  `ui_grounding`.
- Add a validation pass that checks the `value` field of every `VisionFact` for
  action-directive patterns.
- Consider using a whitelist of allowed fact_type values rather than accepting
  any string.
- Add a max-length cap on `value` fields to prevent injection of long payloads.

---

## Finding: Lease Store Accumulates Expired Lease IDs But Only Cleans DOWN Keys
(SEVERITY: MEDIUM)

**What is wrong:**
`InputLeaseStore.expire_due()` only removes leases that have `_has_down_key`
(i.e., at least one key in DOWN state). If a lease has all keys in UP state and
only a `mouse_delta`, it is never expired. While `_apply_lease` only calls
`self._lease_store.add(lease)` when there is at least one DOWN key, there is no
mechanism to remove stale UP-only leases that might be added through other code
paths.

More critically, `InputLeaseStore` uses a flat `dict[str, InputLease]` with no
size bound. Each unique `lease_id` is a new entry. If a lease source generates
high-frequency leases with unique IDs (e.g., one per frame for mouse movements),
the dict grows unbounded over 30 minutes.

**Why it matters for long sessions:**
At 30fps with mouse-only leases (UP-only after application), if any code path
stores them, memory grows linearly. Even if current code paths do not store
UP-only leases, the absence of a size bound is a latent risk for 30-minute
sessions.

**Concrete scenario:**
A controller generates 1800 leases per minute (30fps). If any code path adds
UP-only leases to the store (or if a lease validation is bypassed), the dict
grows to ~54,000 entries in 30 minutes. Each entry holds a reference to an
`InputLease` with dict payload.

**Suggested fix:**
- Add a max-size eviction policy to `InputLeaseStore` (e.g., cap at 1000
  entries, evict oldest).
- Add a periodic sweep that removes leases past their expiry regardless of
  key state.
- Add a health metric: `len(self._leases)` published to telemetry.

---

## Finding: SafeWindowBackend Focus Detection Can Produce False Positives on Window Rename
(SEVERITY: HIGH)

**What is wrong:**
`SafeWindowInputBackend.is_target_focused()` calls `_find_target_window()` which
uses `FindWindowW(None, title)` with exact title match. Windows can change their
title dynamically (e.g., Genshin Impact appends region names, loading states, or
FPS counters to the title bar). If the title changes, `FindWindowW` returns 0,
`_find_target_window` raises `SafeWindowInputError`, and `is_target_focused`
returns `False`.

When this happens, `_ensure_target_focused` attempts `_force_foreground`, sleeps
100ms, and if still not focused, calls `release_all` and raises. This means a
spontaneous window title change triggers an emergency release.

There is no fuzzy matching, no window class matching, and no process ID
matching in the focus check. The `alt_window_titles` list is checked but only
with exact string match.

**Why it matters for long sessions:**
Games frequently update their window titles with loading screen info, character
names, or region names. Over 30 minutes, the probability of at least one title
change is high. Each false-positive focus loss triggers `release_all` +
emergency interrupt, causing the agent to lose all held keys and enter recovery
mode.

**Concrete scenario:**
The testbed window title changes from "Aurora Genshin-like Testbed" to
"Aurora Genshin-like Testbed [Loading...]" during a zone transition. Focus
detection fails. All keys are released mid-combat. The agent enters emergency
stop.

**Suggested fix:**
- Add process ID (PID) tracking as a fallback: store the PID at first
  successful window find, and use `GetWindowThreadProcessId` for subsequent
  focus checks when title match fails.
- Add window class name matching as an additional identifier.
- Implement substring/prefix matching with a configurable match policy
  (exact, prefix, contains).
- Add a "focus grace period": if focus was recently confirmed, require N
  consecutive failures before triggering emergency release.

---

## Finding: `_ensure_target_focused` Uses `time.sleep(0.1)` Blocking the Worker Thread
(SEVERITY: MEDIUM)

**What is wrong:**
`SafeWindowInputBackend._ensure_target_focused()` calls `time.sleep(0.1)` after
attempting to force the window to the foreground. This violates the project's
own "no blocking waits" design rule. In the context of the `InputWorker` event
loop, this blocks the deadman check and all pending lease processing for 100ms.

**Why it matters for long sessions:**
If focus is repeatedly lost and regained (e.g., notification popups stealing
focus), this 100ms sleep accumulates. Over 30 minutes with frequent focus
fluctuations, the worker thread can spend significant time sleeping rather than
processing leases and deadman checks, potentially allowing expired leases to
linger.

**Concrete scenario:**
Windows notifications steal focus every 2 minutes. Each time, the input worker
sleeps 100ms. If the agent is mid-action-block with a 500ms lease, the 100ms
delay means the deadman check runs late, and the lease expires before the
worker can release the key naturally.

**Suggested fix:**
- Replace `time.sleep(0.1)` with a chunked wait loop checking the stop event:
  `for _ in range(10): time.sleep(0.01); if self.is_target_focused(): break`.
- Or better, make `_ensure_target_focused` non-blocking by returning a
  "pending focus" status and deferring the action to the next tick.

---

## Finding: Vision Fact Bundle Can Be Internally Contradictory
(SEVERITY: HIGH)

**What is wrong:**
`_parse_fact_bundle()` in `gemma_vision_provider.py` builds a `VisionFactBundle`
with:
- A top-level `screen_state` string.
- A list of `VisionFact` objects, each with its own `fact_type` and `value`.
- A top-level `uncertainty` float.

There is no cross-validation between these fields. The VLM can return:
```json
{
  "screen_state": "combat",
  "uncertainty": 0.1,
  "facts": [
    {"fact_type": "screen_state", "value": "menu", "confidence": 0.95},
    {"fact_type": "ui_grounding", "value": "health bar", "confidence": 0.8, "bbox_norm": [0.0, 0.0, 0.5, 0.5]},
    {"fact_type": "ui_grounding", "value": "health bar", "confidence": 0.9, "bbox_norm": [0.5, 0.5, 0.5, 0.5]}
  ]
}
```

This bundle claims screen is "combat" with low uncertainty, but contains a
contradictory screen_state fact claiming "menu". It also contains two
overlapping grounding facts for the same element with different bboxes. No
deduplication or contradiction detection exists.

**Why it matters for long sessions:**
Downstream planning uses `screen_state` for mode transitions and `facts` for
action selection. Contradictory facts can cause rapid mode oscillation (combat
-> menu -> combat within 100ms), triggering repeated emergency interrupts and
recovery loops.

**Concrete scenario:**
The VLM is uncertain about a loading screen transition and returns
screen_state="combat" but includes a fact with fact_type="screen_state",
value="loading". The mode arbiter sees "combat" and allows aggressive actions,
while the fact pipeline detects "loading" and triggers recovery. The agent
oscillates between combat and recovery every frame.

**Suggested fix:**
- Add a `validate_consistency()` method to `VisionFactBundle` or its builder
  that checks:
  - All facts of type `screen_state` agree with the top-level `screen_state`.
  - No two `ui_grounding` facts have >80% bbox overlap with different labels.
  - `uncertainty` is consistent with fact confidence spread.
- Reject or flag bundles with contradictions, forcing a re-query or fallback.

---

## Finding: HTTP Connections in Local VLM Provider Are Not Pooled and May Leak
(SEVERITY: MEDIUM)

**What is wrong:**
`OpenAICompatibleLocalVisionProvider._chat()` and `status()` both use
`urllib.request.urlopen()` with `with` context managers. While the `with` block
ensures the response is closed, `urllib.request` creates a new HTTP connection
for every call. Python's `urllib` does use connection reuse via
`http.client.HTTPConnection` internally, but only for the same host within a
short time window.

Over 30 minutes at 2-5 VLM calls per second (one per frame for fact extraction),
this creates ~3600-9000 HTTP connections. Each connection that is not properly
reused occupies a file descriptor and socket until the OS reclaims it.

There is no `ConnectionPool` or `requests.Session` equivalent. There is no
explicit connection close or cleanup. If the VLM server becomes slow, the
`timeout_sec` (default 20s) means many connections can be simultaneously open.

**Why it matters for long sessions:**
On Windows, the default socket limit is around 8192 file descriptors (adjusted
by registry). At high VLM query rates with slow responses, the system can
exhaust available sockets, leading to `OSError: [WinError 10048]` (address
already in use) or connection timeouts that cascade into perception failures.

**Concrete scenario:**
The VLM takes 3 seconds per request on average. At 2 QPS, there are typically
6 concurrent connections. If the VLM becomes slow (15s per request) due to GPU
contention, the number of concurrent connections rises to 30+, and timed-out
connections linger in TIME_WAIT state for 120 seconds. After 20 minutes of
degraded VLM performance, the agent cannot open new connections.

**Suggested fix:**
- Replace `urllib.request` with `requests.Session` or `httpx.Client` for proper
  connection pooling with configurable pool size.
- Add a connection pool health metric to `status()`.
- Add a circuit breaker: if N consecutive requests fail or time out, stop
  sending requests for a cooling period and fall back to deterministic mode.

---

## Finding: ConsoleInputBackend Event List Is Unbounded After Truncation Threshold
(SEVERITY: LOW)

**What is wrong:**
`ConsoleInputBackend._events` list is capped at `self._max_events = 10000`, but
the truncation in `_record()` uses list slicing:
```python
if len(self._events) > self._max_events:
    self._events = self._events[-self._max_events:]
```
This creates a new list every time the threshold is exceeded. Over 30 minutes at
30fps input rate, this creates ~54,000 events. The list is sliced every time it
exceeds 10,000, which happens roughly every 5.5 minutes. Each slice copies
10,000 event objects.

The `events_snapshot()` method also copies the entire list each time it is
called.

**Why it matters for long sessions:**
Minor GC pressure from repeated list allocations. Not a crash risk but
contributes to memory churn over long sessions.

**Suggested fix:**
- Use `collections.deque(maxlen=10000)` instead of a list for O(1) append and
  automatic eviction.
- `events_snapshot()` returns `list(self._events)` which works with deque.

---

## Finding: Profile Switching Has No Safety Guard -- Active Leases Not Invalidated
(SEVERITY: HIGH)

**What is wrong:**
`CalibrationStore.save_profile()` can overwrite the active profile and change
`window_title`, `source_resolution`, and `rois` at any time. There is no lock
between profile mutation and active input backend usage.

If the profile's `window_title` changes while `SafeWindowInputBackend` is
running, the next `_find_target_window()` call will look for the old title
(which no longer exists) and fail. This triggers a false focus-loss event and
emergency key release.

There is also no validation that the new profile's `normalized_resolution`
matches the running perception pipeline's expected resolution. An ROI defined
for 720p applied to a 1080p capture will produce incorrect coordinates.

`SafeWindowInputBackend` stores `target_window_title` at construction time and
never reloads it from the profile store.

**Why it matters for long sessions:**
If a user updates a calibration profile while the agent is running (e.g.,
adjusting ROI boundaries), the agent's window targeting and coordinate systems
silently diverge from the actual profile. Actions computed against old ROI
boundaries are applied to a window with new boundaries.

**Concrete scenario:**
User adjusts the genshin profile's `skill_buttons` ROI from `[0.76, 0.84,
0.22, 0.12]` to `[0.78, 0.86, 0.18, 0.10]` while the agent is mid-combat.
The perception pipeline still uses the old ROI coordinates for the next 2-3
frames. The agent "sees" skill buttons in the wrong position and clicks empty
space instead of using the correct skill.

**Suggested fix:**
- Add a `profile_version` counter. `SafeWindowInputBackend` should check the
  version before each action and reload if changed.
- Add a `profile_lock` that prevents profile mutation while the agent has active
  leases.
- When a profile changes, emit a `ModeRequest` to enter a safe idle mode until
  the perception pipeline reloads.

---

## Finding: VisionOutputGuard Blocks Legitimate Game Vocabulary, Causing False Positive Rejection
(SEVERITY: MEDIUM)

**What is wrong:**
The `_BLOCKED_TERMS` list includes common words: "click", "press", "type",
"execute", "cmd", "driver", "inject", "memory". In game contexts, these words
appear legitimately in UI text:
- "Press F to interact" (common interaction prompt)
- "Click to continue" (dialog prompt)
- "Memory" (character memory system in some games)
- "Type" (element type in Genshin: "Anemo type")

The guard rejects any candidate whose `label` or `reason` contains these terms.
In `_parse_fact_bundle`, rejected candidates are silently discarded (the `continue`
statement). Over 30 minutes, this can filter out a significant fraction of
legitimate UI elements.

**Why it matters for long sessions:**
The agent loses access to interaction prompts, dialog options, and UI elements
that contain these words. This creates blind spots that accumulate over time.
The agent may fail to detect "Press F to interact" prompts for 30 minutes
straight, making it unable to complete any interaction.

**Concrete scenario:**
The VLM returns a fact: `{"fact_type": "ocr_text_hint", "value": "Press F to
collect reward", "confidence": 0.9}`. If this goes through `validate_candidate`
(e.g., as a ui_grounding fact), it is rejected because the label contains
"Press". The agent never sees the interaction prompt and wanders aimlessly.

**Suggested fix:**
- Replace the static blocklist with contextual analysis: only reject if the
  text contains action directives directed AT the agent (imperative mood, not
  descriptive game text).
- Add a whitelist of game-specific phrases that are allowed despite containing
  blocked terms.
- Move the blocklist to a configurable file so game-specific overrides are
  possible without code changes.
- Log rejected candidates at WARN level so operators can identify false
  positives during development.

---

## Finding: ModelRouter Has No Persistent Health State -- Every Decision Starts Fresh
(SEVERITY: MEDIUM)

**What is wrong:**
`ModelRoutePolicy.decide()` is stateless. It takes `local_status` and
`bench_result` as parameters each time, but the caller must supply these. There
is no mechanism to track:
- How many consecutive local VLM failures have occurred.
- Whether the local VLM has been consistently slow for the last N minutes.
- Whether a fallback was recently activated.

Without this state, the router cannot implement hysteresis or circuit-breaking.
After a local VLM failure, the next call with a fresh `status()` check (which
might succeed if the server just restarted) will immediately route back to local
VLM, even if it is in a degraded state.

**Why it matters for long sessions:**
The agent oscillates between local VLM and fallback on every frame. If the VLM
is in a "flapping" state (works intermittently), the router sends requests to
it, they fail, then it falls back, then the next status check succeeds, it
tries again, fails again. This oscillation wastes time and produces
inconsistent perception quality.

**Concrete scenario:**
LM Studio has a memory leak that causes it to slow down after 15 minutes. Every
5th request times out. The router sees "status ok" (because status is a fast
GET), routes to local VLM, the request times out, falls back to deterministic.
Next frame: same cycle. The agent's perception alternates between rich VLM
output and sparse deterministic output every few frames, causing jerky behavior.

**Suggested fix:**
- Add a `ModelRouterState` class that tracks:
  - Consecutive failure count with configurable threshold before circuit-break.
  - Exponential backoff timer before retrying a failed backend.
  - Rolling window of latencies for trend detection.
- Implement a circuit breaker: after N failures in a row, disable the backend
  for a cooling period, then try again with a single probe request.

---

## Finding: InputWorker Thread Exception Handling Does Not Publish StateBus Interrupt
(SEVERITY: MEDIUM)

**What is wrong:**
In `_run_loop()`, the `BaseException` handler (line 108-116) catches fatal
exceptions and forces `release_all`, but it does **not** publish an interrupt to
the StateBus. The `finally` block also does not publish.

This means if the input worker crashes, the rest of the kernel (control loop,
orchestration) has no explicit notification. They will eventually notice via the
heartbeat table or watchdog, but there is a gap where the system believes the
worker is alive and responsive.

**Why it matters for long sessions:**
If the worker thread dies at minute 25 due to an unhandled ctypes error (e.g.,
`SendInput` fails with an access violation), all keys are released locally, but
the control loop continues to submit leases. These leases queue up in the
command queue (max 1024) and are never processed. When the queue fills, new
leases are silently dropped. The system appears to be running but no input is
being delivered.

**Concrete scenario:**
A Windows update changes the input API behavior. `SendInput` starts returning 0
intermittently. `SafeWindowInputBackend` raises `SafeWindowInputError` inside
the worker's `_apply_lease`. This is caught by the `BaseException` handler. The
worker exits after releasing keys. But the control loop keeps running, queuing
leases that are never processed.

**Suggested fix:**
- In the `BaseException` handler, if `self._state_bus` is available, publish a
  P0 `WORKER_CRASHED` interrupt.
- In the `finally` block, publish a `WORKER_STOPPED` event.
- Add a liveness check: the control loop should verify `worker.is_alive` before
  submitting leases and enter a safe mode if the worker is dead.

---

## Finding: `_force_foreground` Can Deadlock with Window Focus Race
(SEVERITY: MEDIUM)

**What is wrong:**
`SafeWindowInputBackend._force_foreground()` uses `AttachThreadInput` to
attach the current thread's input to the foreground window's thread. This is a
Win32 API that can cause deadlocks if both threads are trying to manipulate
focus simultaneously.

Additionally, `AttachThreadInput(cur_tid, fg_tid, False)` is called in the
`finally` block, but if `fg_tid` is 0 (which `GetWindowThreadProcessId` returns
for the desktop window), `AttachThreadInput` may fail silently or produce
undefined behavior.

**Why it matters for long sessions:**
Over 30 minutes, focus stealing events can happen dozens of times. Each time
`_force_foreground` is called, there is a risk of a brief deadlock. If the
input worker thread is blocked in `_force_foreground`, it cannot process
deadman checks, and keys remain held past their lease expiry.

**Concrete scenario:**
A notification popup steals focus. The input worker calls `_force_foreground`,
which calls `AttachThreadInput`. Simultaneously, the popup's animation thread
is also calling `SetForegroundWindow`. Both threads block on the Win32 focus
lock. The input worker is stuck for 200-500ms, during which the deadman check
does not run and a held key (W for "walk forward") remains pressed.

**Suggested fix:**
- Add a timeout to `_force_foreground` using a bounded wait.
- Add `AttachThreadInput` error checking and skip if the foreground thread is
  the desktop window (thread ID 0).
- Consider not attempting `_force_foreground` at all and simply fail the action
  if focus is lost. This is safer than risking a deadlock.

---

## Finding: LLMRequestGuard Uses `time.time()` Instead of `time.perf_counter()`
(SEVERITY: LOW)

**What is wrong:**
`LLMRequestGuard.check()` uses `time.time()` for rate-limiting timestamps. The
project rules mandate `time.perf_counter()` for all logic timing. `time.time()`
is subject to system clock adjustments (NTP corrections, manual changes), which
can cause the rate limiter to behave incorrectly:
- A backward clock jump makes the guard think less time has passed, allowing
  bursts.
- A forward clock jump makes the guard think more time has passed, rejecting
  legitimate requests.

**Why it matters for long sessions:**
Over 30 minutes, an NTP correction is plausible. If the clock jumps backward
by 1 second, the guard's 60-second window check may allow a burst of 6+ calls
in rapid succession.

**Suggested fix:**
- Replace `time.time()` with `time.perf_counter()` in `LLMRequestGuard.check()`.

---

## Finding: Benchmark Suite Uses Single Pixel PNG -- Results Not Representative
(SEVERITY: LOW)

**What is wrong:**
`LocalVlmBench.run_smoke()` uses `_one_pixel_png()` -- a 1x1 pixel PNG -- for
all test queries. This means:
- `classify_screen` accuracy is always 100% (any answer matches one of 3 states).
- `ground_ui_success_rate` measures whether the VLM returns parseable JSON from
  a blank image, not whether it can actually locate UI elements.
- Latency measurements reflect minimum response time with no actual image
  processing, not real-world latency.

The `json_valid_rate` calculation divides by 3.0 but can count up to 6 JSON
responses (screen, ui, failure, quest, dialogue, marker), making the rate
artificially low when optional smokes pass.

**Why it matters for long sessions:**
If the bench results are used for routing decisions (`ModelRoutePolicy` checks
`bench_result.ui_grounding_success_rate`), the artificially high success rate
from blank-image testing will keep the local VLM routed even when it cannot
actually ground UI elements in real game frames.

**Suggested fix:**
- Add real game frame samples (even synthetic ones) to the bench.
- Or document clearly that `run_smoke` is a connectivity/format smoke test, not
  an accuracy benchmark, and should not be used for routing decisions.
- Separate connectivity smoke from accuracy bench with different thresholds.

---

## Summary Table

| # | Severity | Title |
|---|----------|-------|
| 1 | CRITICAL | No failover when Gemma backend goes down mid-session |
| 2 | HIGH | Vision output guard bypass via non-grounding fact types |
| 3 | MEDIUM | Lease store unbounded growth risk |
| 4 | HIGH | Focus detection fails on window title change |
| 5 | MEDIUM | Blocking sleep in `_ensure_target_focused` |
| 6 | HIGH | Vision fact bundle internal contradictions undetected |
| 7 | MEDIUM | HTTP connections not pooled, risk of socket exhaustion |
| 8 | LOW | ConsoleBackend event list GC churn |
| 9 | HIGH | Profile switch does not invalidate active leases or reload backend |
| 10 | MEDIUM | Output guard false positives block legitimate game vocabulary |
| 11 | MEDIUM | ModelRouter stateless -- no circuit breaker or hysteresis |
| 12 | MEDIUM | Worker crash does not publish StateBus interrupt |
| 13 | MEDIUM | `_force_foreground` deadlock risk |
| 14 | LOW | LLMRequestGuard uses wall clock instead of monotonic |
| 15 | LOW | Benchmark uses blank image, results not representative |

**Critical path for 30-minute safe operation:**
Findings 1, 4, and 9 form the most dangerous combination. If the VLM crashes
(finding 1), the agent has no fallback and crashes. If the window title changes
(finding 4), the agent triggers false emergency stops. If a profile is updated
during the session (finding 9), coordinate systems silently diverge. Together,
these three guarantee that a 30-minute session will experience at least one
unhandled failure mode under realistic conditions.
