import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  BookOpen,
  Bot,
  Gauge,
  Library,
  Pause,
  Play,
  Radar,
  RotateCw,
  Settings,
  ShieldCheck,
  Square,
  WandSparkles,
} from "lucide-react";
import "./styles.css";

type AgentState = {
  mode: "STOPPED" | "RUNNING" | "PAUSED" | "EMERGENCY_STOPPED";
  current_node: string;
  current_skill: string | null;
  target_state: string;
  progress: number;
  frustration: number;
  input_backend: string;
  focus_status: string;
  active_interrupt: Record<string, unknown> | null;
  runtime_health: {
    healthy: boolean;
    input_worker_alive: boolean;
    telemetry_ok: boolean;
    release_all_called: boolean;
    updated_at: number;
  };
  input_released: boolean;
  telemetry_ok: boolean;
  latest_run_id: string | null;
  updated_at: number;
};

type Page = "dashboard" | "monitor" | "reports" | "settings" | "calibration" | "skills" | "planner" | "companion" | "combat" | "checklist";

type WindowSummary = {
  title: string;
  pid: number;
  handle: number;
  rect: { left: number; top: number; right: number; bottom: number; width: number; height: number };
  focused: boolean;
  visible: boolean;
};

type RoiDraft = {
  name: string;
  mode: "relative" | "anchor";
  anchor: "top-left" | "top-right" | "bottom-left" | "bottom-right" | "center";
  rect: { x: number; y: number; w: number; h: number };
};

type ModelStatus = {
  detector_backend: string;
  model_path: string | null;
  model_exists: boolean;
  ultralytics_available: boolean;
  tracker: string;
  tracker_available: boolean;
  device: string;
  half: boolean;
};

type SkillSummary = {
  skill_id: string;
  name: string;
  type: string;
  version: number;
  archived?: boolean;
};

type ChecklistItem = {
  key: string;
  label: string;
  ok: boolean;
  detail: string;
};

type PersonaProfile = {
  persona_id: string;
  name: string;
  style: string;
  tone: string;
};

const API = "http://127.0.0.1:8765";
const WS = "ws://127.0.0.1:8765/ws/state";

const fallbackState: AgentState = {
  mode: "STOPPED",
  current_node: "INIT",
  current_skill: null,
  target_state: "NONE",
  progress: 0,
  frustration: 0,
  input_backend: "console",
  focus_status: "DISCONNECTED",
  active_interrupt: null,
  runtime_health: {
    healthy: true,
    input_worker_alive: false,
    telemetry_ok: true,
    release_all_called: true,
    updated_at: 0,
  },
  input_released: true,
  telemetry_ok: true,
  latest_run_id: null,
  updated_at: 0,
};

function App() {
  const [state, setState] = useState<AgentState>(fallbackState);
  const [page, setPage] = useState<Page>("dashboard");
  const [events, setEvents] = useState<string[]>([]);
  const [report, setReport] = useState<string>("");
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    fetch(`${API}/state`).then((r) => r.json()).then(setState).catch(() => undefined);
    const socket = new WebSocket(WS);
    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onmessage = (message) => {
      const next = JSON.parse(message.data) as AgentState;
      setState(next);
      setEvents((items) => [
        `${new Date().toLocaleTimeString()} ${next.mode} ${next.current_node} ${next.target_state}`,
        ...items.slice(0, 30),
      ]);
    };
    return () => socket.close();
  }, []);

  useEffect(() => {
    if (page !== "reports") return;
    fetch(`${API}/runs/latest`)
      .then((r) => r.json())
      .then((data) => setReport(data.report_markdown ?? ""))
      .catch(() => setReport(""));
  }, [page]);

  const command = async (path: string) => {
    const response = await fetch(`${API}${path}`, { method: "POST" });
    const payload = await response.json();
    setState(payload.state);
  };

  const nav = useMemo(
    () => [
      ["dashboard", "Dashboard", Bot],
      ["monitor", "Run Monitor", Activity],
      ["reports", "Reports", BookOpen],
      ["settings", "Settings", Settings],
      ["calibration", "Calibration", Radar],
      ["skills", "Skill Library", Library],
      ["planner", "Task Planner", WandSparkles],
      ["companion", "Companion", Bot],
      ["combat", "Combat", Gauge],
      ["checklist", "Product Demo", ShieldCheck],
    ] as const,
    [],
  );

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brandMark">A</div>
          <div>
            <div className="brandTitle">Aurora Agent</div>
            <div className="brandSub">Vision Kernel Shell</div>
          </div>
        </div>
        <nav>
          {nav.map(([id, label, Icon]) => (
            <button key={id} className={page === id ? "nav active" : "nav"} onClick={() => setPage(id)}>
              <Icon size={18} />
              {label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="main">
        <header className="topbar">
          <div>
            <div className="eyebrow">Local Service {connected ? "Connected" : "Offline"}</div>
            <h1>{pageTitle(page)}</h1>
          </div>
          <div className={`modePill ${state.mode.toLowerCase()}`}>{state.mode}</div>
        </header>
        {page === "dashboard" && <Dashboard state={state} command={command} navigate={setPage} />}
        {page === "monitor" && <RunMonitor state={state} events={events} />}
        {page === "reports" && <Reports report={report} runId={state.latest_run_id} />}
        {page === "settings" && <SettingsPage state={state} />}
        {page === "calibration" && <CalibrationWizard />}
        {page === "skills" && <SkillLibrary />}
        {page === "planner" && <TaskPlanner />}
        {page === "companion" && <CompanionOverlay />}
        {page === "combat" && <CombatPanel />}
        {page === "checklist" && <ProductChecklist />}
      </main>
    </div>
  );
}

function Dashboard({ state, command, navigate }: { state: AgentState; command: (path: string) => Promise<void>; navigate: (page: Page) => void }) {
  const [diagnostics, setDiagnostics] = useState<Record<string, unknown> | null>(null);
  const runDiagnostics = async () => {
    const data = await fetch(`${API}/diagnostics/run`, { method: "POST" }).then((r) => r.json());
    setDiagnostics(data);
  };
  return (
    <section className="grid">
      <div className="heroPanel">
        <div className="avatarRing">
          <Bot size={64} />
        </div>
        <div>
          <div className="eyebrow">Dry-run default</div>
          <h2>{state.current_node}</h2>
          <p>{state.current_skill ?? "No active skill"}</p>
        </div>
      </div>
      <div className="commandPanel">
        <button className="cmd start" onClick={() => command("/agent/start")}><Play size={18} />Start</button>
        <button className="cmd" onClick={() => command("/agent/pause")}><Pause size={18} />Pause</button>
        <button className="cmd" onClick={() => command("/agent/resume")}><RotateCw size={18} />Resume</button>
        <button className="cmd" onClick={() => command("/agent/stop")}><Square size={18} />Stop</button>
        <button className="cmd emergency" onClick={() => command("/agent/emergency_stop")}>
          <AlertTriangle size={19} />Emergency Stop
        </button>
      </div>
      <div className="commandPanel">
        <button className="cmd start" onClick={() => command("/agent/start")}><Play size={18} />Start Local Service</button>
        <button className="cmd" onClick={() => runDiagnostics()}><ShieldCheck size={18} />Run Diagnostics</button>
        <button className="cmd" onClick={() => navigate("calibration")}><Radar size={18} />Open Calibration</button>
        <button className="cmd" onClick={() => navigate("skills")}><Library size={18} />Open Skill Library</button>
        {diagnostics && <pre>{JSON.stringify(diagnostics, null, 2)}</pre>}
      </div>
      <StatusCard label="Focus OK" value={state.focus_status} ok={state.focus_status === "DRY_RUN"} />
      <StatusCard label="Input Released" value={state.input_released ? "Released" : "Held"} ok={state.input_released} />
      <StatusCard label="Telemetry OK" value={state.telemetry_ok ? "Streaming" : "Backpressure"} ok={state.telemetry_ok} />
      <StatusCard label="Runtime Health" value={state.runtime_health.healthy ? "Healthy" : "Attention"} ok={state.runtime_health.healthy} />
    </section>
  );
}

function RunMonitor({ state, events }: { state: AgentState; events: string[] }) {
  return (
    <section className="monitor">
      <div className="metricPanel">
        <Metric icon={<Gauge size={20} />} label="Progress" value={`${Math.round(state.progress * 100)}%`} />
        <Metric icon={<AlertTriangle size={20} />} label="Frustration" value={state.frustration.toFixed(1)} />
        <Metric icon={<Radar size={20} />} label="Target" value={state.target_state} />
        <Metric icon={<ShieldCheck size={20} />} label="Interrupt" value={state.active_interrupt ? String(state.active_interrupt.code) : "None"} />
      </div>
      <div className="eventStream">
        <h2>Event Stream</h2>
        {events.length ? events.map((event, index) => <div className="event" key={index}>{event}</div>) : <div className="empty">Waiting for state frames...</div>}
      </div>
    </section>
  );
}

function Reports({ report, runId }: { report: string; runId: string | null }) {
  const [activeReport, setActiveReport] = useState(report);
  const [activeTitle, setActiveTitle] = useState(runId ?? "Latest Run");
  useEffect(() => setActiveReport(report), [report]);
  const loadReport = async (path: string, title: string) => {
    const data = await fetch(`${API}${path}`).then((r) => r.json());
    setActiveTitle(data.run_id ?? title);
    setActiveReport(data.report_markdown ?? "");
  };
  return (
    <section className="reportPanel">
      <div className="reportHeader">
        <div>
          <div className="eyebrow">Report Reader</div>
          <h2>{activeTitle}</h2>
        </div>
        <div className="reportActions">
          <button className="cmd" onClick={() => loadReport("/runs/latest", "Latest Kernel Run")}>Kernel</button>
          <button className="cmd" onClick={() => loadReport("/product/latest_report", "Latest Product Report")}>Product</button>
          <button className="cmd start" onClick={() => loadReport("/showcase/latest_report", "Latest Showcase Report")}>Showcase</button>
        </div>
      </div>
      {activeReport ? <pre>{activeReport}</pre> : <div className="empty">No report found. Run a demo, then choose Kernel, Product, or Showcase.</div>}
    </section>
  );
}

function SettingsPage({ state }: { state: AgentState }) {
  return (
    <section className="settingsPanel">
      <StatusCard label="Input Backend" value={state.input_backend} ok={state.input_backend === "console"} />
      <StatusCard label="Real Input" value="Disabled by default" ok />
      <StatusCard label="Safe Window" value="Required for physical input" ok />
      <StatusCard label="F9 Stop" value="Enabled in runners" ok />
    </section>
  );
}

function CalibrationWizard() {
  const [step, setStep] = useState(1);
  const [runMode, setRunMode] = useState("Sandbox Demo");
  const [windows, setWindows] = useState<WindowSummary[]>([]);
  const [selected, setSelected] = useState<WindowSummary | null>(null);
  const [snapshotVersion, setSnapshotVersion] = useState(0);
  const [roiName, setRoiName] = useState("main_view");
  const [roiMode, setRoiMode] = useState<"relative" | "anchor">("relative");
  const [anchor, setAnchor] = useState<RoiDraft["anchor"]>("top-right");
  const [rois, setRois] = useState<RoiDraft[]>([]);
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [draftRect, setDraftRect] = useState<RoiDraft["rect"] | null>(null);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [benchmark, setBenchmark] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("Choose a mode to begin.");
  const imageRef = useRef<HTMLImageElement | null>(null);

  const refreshWindows = async () => {
    const data = await fetch(`${API}/windows`).then((r) => r.json());
    setWindows(data.windows ?? []);
    setMessage(data.windows?.length ? "Select the target window from the list." : "No target window found. Start the test environment first.");
  };

  const selectWindow = async (window: WindowSummary) => {
    const data = await fetch(`${API}/window/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ handle: window.handle }),
    }).then((r) => r.json());
    if (data.detail) {
      setMessage(data.detail);
      return;
    }
    setSelected(data.window);
    setSnapshotVersion(Date.now());
    setMessage("Window selected. Review the live snapshot before drawing ROIs.");
  };

  const refreshModel = async () => {
    setModelStatus(await fetch(`${API}/models/status`).then((r) => r.json()));
  };

  const runBenchmark = async () => {
    setBenchmark(await fetch(`${API}/models/benchmark`, { method: "POST" }).then((r) => r.json()));
  };

  const saveProfile = async () => {
    if (!selected) {
      setMessage("Select a target window before saving a profile.");
      return;
    }
    const profileId = `profile_${selected.rect.width}x${selected.rect.height}`;
    const payload = {
      profile: {
        profile_id: profileId,
        window_title: selected.title,
        source_resolution: [selected.rect.width, selected.rect.height],
        normalized_resolution: [1280, 720],
        rois: Object.fromEntries(rois.map((roi) => [roi.name, roiToPayload(roi, selected)])),
      },
      activate: true,
    };
    const saved = await fetch(`${API}/calibration/profile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) => r.json());
    const tested = await fetch(`${API}/calibration/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile_id: saved.profile_id }),
    }).then((r) => r.json());
    setMessage(tested.ok ? `Profile ${saved.profile_id} saved and validated.` : `Profile saved but needs review: ${tested.errors?.join(", ")}`);
  };

  const startDrag = (event: React.MouseEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width;
    const y = (event.clientY - box.top) / box.height;
    setDragStart({ x, y });
    setDraftRect({ x, y, w: 0, h: 0 });
  };

  const updateDrag = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!dragStart) return;
    const box = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width;
    const y = (event.clientY - box.top) / box.height;
    setDraftRect({
      x: Math.min(dragStart.x, x),
      y: Math.min(dragStart.y, y),
      w: Math.abs(x - dragStart.x),
      h: Math.abs(y - dragStart.y),
    });
  };

  const endDrag = () => {
    if (!draftRect || draftRect.w < 0.01 || draftRect.h < 0.01) {
      setDragStart(null);
      return;
    }
    setRois((items) => [
      ...items.filter((item) => item.name !== roiName),
      { name: roiName, mode: roiMode, anchor, rect: draftRect },
    ]);
    setDragStart(null);
    setDraftRect(null);
    setMessage(`${roiName} ROI captured. Add more ROIs or continue.`);
  };

  useEffect(() => {
    refreshWindows().catch(() => setMessage("Could not load windows. Is the service running?"));
    refreshModel().catch(() => undefined);
  }, []);

  const progress = Math.round((step / 6) * 100);

  return (
    <section className="wizard">
      <div className="wizardHeader">
        <div>
          <div className="eyebrow">First-run setup</div>
          <h2>Calibration Wizard</h2>
          <p>{message}</p>
        </div>
        <div className="progressTrack"><div style={{ width: `${progress}%` }} /></div>
      </div>
      <div className="wizardSteps">
        {[1, 2, 3, 4, 5, 6].map((item) => (
          <button key={item} className={step === item ? "step active" : "step"} onClick={() => setStep(item)}>Step {item}</button>
        ))}
      </div>
      {step === 1 && (
        <div className="wizardPanel optionGrid">
          {["Sandbox Demo", "QA Environment", "Analysis Only", "Dry-run Only"].map((mode) => (
            <button className={runMode === mode ? "option active" : "option"} key={mode} onClick={() => setRunMode(mode)}>
              <strong>{mode}</strong>
              <span>{mode === "Dry-run Only" ? "No physical input will be used." : "Guided setup with dry-run safety defaults."}</span>
            </button>
          ))}
        </div>
      )}
      {step === 2 && (
        <div className="wizardPanel splitPanel">
          <div>
            <button className="cmd" onClick={refreshWindows}>Refresh Windows</button>
            <div className="windowList">
              {windows.map((window) => (
                <button key={window.handle} className={selected?.handle === window.handle ? "windowRow active" : "windowRow"} onClick={() => selectWindow(window)}>
                  <strong>{window.title}</strong>
                  <span>{window.rect.width}x{window.rect.height} pid={window.pid} {window.focused ? "focused" : ""}</span>
                </button>
              ))}
            </div>
          </div>
          <Snapshot selected={selected} snapshotVersion={snapshotVersion} />
        </div>
      )}
      {step === 3 && (
        <div className="wizardPanel roiLayout">
          <div className="roiToolbar">
            <select value={roiName} onChange={(event) => setRoiName(event.target.value)}>
              {["main_view", "target_area", "minimap", "skill_bar", "status_area", "dialog_area", "interaction_prompt_area"].map((name) => <option key={name}>{name}</option>)}
            </select>
            <select value={roiMode} onChange={(event) => setRoiMode(event.target.value as "relative" | "anchor")}>
              <option value="relative">relative</option>
              <option value="anchor">anchor-based</option>
            </select>
            <select value={anchor} onChange={(event) => setAnchor(event.target.value as RoiDraft["anchor"])}>
              {["top-left", "top-right", "bottom-left", "bottom-right", "center"].map((name) => <option key={name}>{name}</option>)}
            </select>
          </div>
          <div className="snapshotBox selectable" onMouseDown={startDrag} onMouseMove={updateDrag} onMouseUp={endDrag}>
            {selected ? <img ref={imageRef} src={`${API}/capture/snapshot?v=${snapshotVersion}`} /> : <div className="empty">Select a window first.</div>}
            {[...rois.map((roi) => roi.rect), ...(draftRect ? [draftRect] : [])].map((rect, index) => <RoiRect key={index} rect={rect} />)}
          </div>
          <div className="roiList">{rois.map((roi) => <div className="event" key={roi.name}>{roi.name}: {roi.mode} {roi.anchor}</div>)}</div>
        </div>
      )}
      {step === 4 && (
        <div className="wizardPanel modelGrid">
          <StatusCard label="Detector" value={modelStatus?.detector_backend ?? "unknown"} ok />
          <StatusCard label="Model File" value={modelStatus?.model_exists ? "Found" : "Missing"} ok={!!modelStatus?.model_exists} />
          <StatusCard label="Ultralytics" value={modelStatus?.ultralytics_available ? "Available" : "Unavailable"} ok={!!modelStatus?.ultralytics_available} />
          <StatusCard label="Tracker" value={`${modelStatus?.tracker ?? "unknown"}`} ok={!!modelStatus?.tracker_available} />
          <button className="cmd start" onClick={runBenchmark}>Run Benchmark</button>
          <div className="eventStream">{benchmark ? JSON.stringify(benchmark, null, 2) : "Benchmark returns capture FPS and latency estimates."}</div>
        </div>
      )}
      {step === 5 && (
        <div className="wizardPanel settingsPanel">
          <StatusCard label="Input Backend" value="dry-run / console" ok />
          <StatusCard label="F9 Emergency Stop" value="Enabled" ok />
          <StatusCard label="Focus Protection" value="Required for safe-window" ok />
          <StatusCard label="release_all Test" value="Available via Emergency Stop" ok />
        </div>
      )}
      {step === 6 && (
        <div className="wizardPanel savePanel">
          <h2>Save Active Profile</h2>
          <p>The profile will be written to configs/profiles, versioned, and set active.</p>
          <button className="cmd start" onClick={saveProfile}>Save Profile</button>
        </div>
      )}
      <div className="wizardFooter">
        <button className="cmd" onClick={() => setStep(Math.max(1, step - 1))}>Back</button>
        <button className="cmd start" onClick={() => setStep(Math.min(6, step + 1))}>Next</button>
      </div>
    </section>
  );
}

function Snapshot({ selected, snapshotVersion }: { selected: WindowSummary | null; snapshotVersion: number }) {
  if (!selected) return <div className="snapshotBox"><div className="empty">Choose a window to preview its screenshot.</div></div>;
  return <div className="snapshotBox"><img src={`${API}/capture/snapshot?v=${snapshotVersion}`} /></div>;
}

function RoiRect({ rect }: { rect: RoiDraft["rect"] }) {
  return <div className="roiRect" style={{ left: `${rect.x * 100}%`, top: `${rect.y * 100}%`, width: `${rect.w * 100}%`, height: `${rect.h * 100}%` }} />;
}

function roiToPayload(roi: RoiDraft, selected: WindowSummary) {
  if (roi.mode === "relative") {
    return { mode: "relative", x: roi.rect.x, y: roi.rect.y, w: roi.rect.w, h: roi.rect.h };
  }
  return {
    mode: "anchor",
    anchor: roi.anchor,
    offset_x_px: Math.round(anchorOffsetX(roi, selected)),
    offset_y_px: Math.round(anchorOffsetY(roi, selected)),
    width_px: Math.round(roi.rect.w * selected.rect.width),
    height_px: Math.round(roi.rect.h * selected.rect.height),
  };
}

function anchorOffsetX(roi: RoiDraft, selected: WindowSummary) {
  const x = roi.rect.x * selected.rect.width;
  if (roi.anchor.endsWith("right")) return x - selected.rect.width;
  if (roi.anchor === "center") return x - selected.rect.width / 2;
  return x;
}

function anchorOffsetY(roi: RoiDraft, selected: WindowSummary) {
  const y = roi.rect.y * selected.rect.height;
  if (roi.anchor.startsWith("bottom")) return y - selected.rect.height;
  if (roi.anchor === "center") return y - selected.rect.height / 2;
  return y;
}

function Placeholder({ title }: { title: string }) {
  return <div className="placeholder"><h2>{title}</h2><p>Planned product module. See docs/ROADMAP.md.</p></div>;
}

function SkillLibrary() {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);
  const [session, setSession] = useState<Record<string, unknown> | null>(null);
  const [log, setLog] = useState("Ready.");

  const refresh = async () => {
    const data = await fetch(`${API}/skills`).then((r) => r.json());
    setSkills(data.skills ?? []);
  };

  const startRecording = async () => {
    const data = await fetch(`${API}/skills/record/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backend: "mock" }),
    }).then((r) => r.json());
    setSession(data.session ?? null);
    setLog(data.message);
  };

  const stopRecording = async () => {
    const data = await fetch(`${API}/skills/record/stop`, { method: "POST" }).then((r) => r.json());
    setDraft(data.draft);
    setSession(null);
    setLog("SkillDraft generated with automatic segments.");
  };

  const addMarker = async () => {
    const data = await fetch(`${API}/skills/record/marker`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ marker: "manual_checkpoint" }),
    }).then((r) => r.json());
    setSession(data.session ?? null);
    setLog("Marker added.");
  };

  const addSampleEvent = async () => {
    const data = await fetch(`${API}/skills/record/event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_type: "mouse_click",
        payload: { button: "left" },
        target_state: "TRACKED",
        focus_state: "FOCUSED",
        visual_triggers: { target_visible: true },
      }),
    }).then((r) => r.json());
    setSession(data.session ?? null);
    setLog("Test-window event captured.");
  };

  const saveDraft = async () => {
    const response = await fetch(`${API}/skills/record/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Recorded Test Window Skill" }),
    });
    const data = await response.json();
    setSelected(data.skill_id ?? null);
    setLog(response.ok ? `Saved draft as ${data.skill_id} v${data.version}` : data.detail);
    refresh();
  };

  const saveDemoSkill = async () => {
    const payload = demoSkillPayload();
    const response = await fetch(`${API}/skills`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    setSelected(data.skill_id ?? null);
    setLog(response.ok ? `Saved ${data.skill_id} v${data.version}` : data.detail);
    refresh();
  };

  const validate = async () => {
    if (!selected) return;
    const data = await fetch(`${API}/skills/${selected}/validate`, { method: "POST" }).then((r) => r.json());
    setLog(data.ok ? "Validation passed." : data.errors.join("\n"));
  };

  const dryRun = async () => {
    if (!selected) return;
    const data = await fetch(`${API}/skills/${selected}/dry_run`, { method: "POST" }).then((r) => r.json());
    setLog((data.result?.payload?.logs ?? []).join("\n") || JSON.stringify(data, null, 2));
  };

  const replay = async () => {
    if (!selected) return;
    const data = await fetch(`${API}/skills/${selected}/replay`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "dry-run", confirm: false }),
    }).then((r) => r.json());
    setLog((data.result?.payload?.logs ?? []).join("\n") || JSON.stringify(data, null, 2));
  };

  useEffect(() => { refresh().catch(() => undefined); }, []);

  return (
    <section className="editorShell">
      <aside className="editorList">
          <button className="cmd start" onClick={startRecording}>Start Recording</button>
          <button className="cmd" onClick={addSampleEvent}>Capture Event</button>
          <button className="cmd" onClick={addMarker}>Marker</button>
          <button className="cmd" onClick={stopRecording}>Stop Recording</button>
          <button className="cmd start" onClick={saveDraft}>Save Draft</button>
          <button className="cmd" onClick={saveDemoSkill}>Save Demo Skill</button>
        {skills.map((skill) => (
          <button key={skill.skill_id} className={selected === skill.skill_id ? "windowRow active" : "windowRow"} onClick={() => setSelected(skill.skill_id)}>
            <strong>{skill.name}</strong>
            <span>{skill.type} v{skill.version}</span>
          </button>
        ))}
      </aside>
      <main className="editorMain">
          <h2>Timeline / Step Tree</h2>
          {draft ? <pre>{JSON.stringify(draft, null, 2)}</pre> : session ? <pre>{JSON.stringify(session, null, 2)}</pre> : <div className="empty">Record or select a skill. The generated draft will show raw events, segments, checkpoints, and fallbacks.</div>}
        </main>
      <aside className="editorProps">
        <h2>Properties</h2>
          <button className="cmd" onClick={validate}>Validate</button>
          <button className="cmd start" onClick={dryRun}>Dry-run</button>
          <button className="cmd" onClick={replay}>Replay Dry-run</button>
          <pre>{log}</pre>
      </aside>
    </section>
  );
}

function TaskPlanner() {
  const [goal, setGoal] = useState("Analyze the sandbox target and complete the verified dry-run flow.");
  const [provider, setProvider] = useState("mock");
  const [personaId, setPersonaId] = useState("default_companion");
  const [personas, setPersonas] = useState<PersonaProfile[]>([]);
  const [plan, setPlan] = useState<Record<string, unknown> | null>(null);
  const [explanation, setExplanation] = useState<Record<string, unknown> | null>(null);

  const runPlanner = async () => {
    const data = await fetch(`${API}/planner/task`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal, provider, persona_id: personaId }),
    }).then((r) => r.json());
    setPlan(data);
  };

  const explain = async () => {
    const data = await fetch(`${API}/planner/explain_failure`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ summary: { failure_code: "TARGET_LOST" }, provider }),
    }).then((r) => r.json());
    setExplanation(data);
  };

  useEffect(() => {
    fetch(`${API}/persona/profiles`).then((r) => r.json()).then((data) => setPersonas(data.personas ?? [])).catch(() => undefined);
  }, []);

  return (
    <section className="plannerPanel">
      <div className="eventStream">
        <h2>Natural Language Goal</h2>
        <textarea value={goal} onChange={(event) => setGoal(event.target.value)} />
        <select value={provider} onChange={(event) => setProvider(event.target.value)}>
          <option value="mock">mock</option>
          <option value="glm">glm</option>
          <option value="minimax">minimax</option>
        </select>
        <select value={personaId} onChange={(event) => setPersonaId(event.target.value)}>
          {personas.map((persona) => <option value={persona.persona_id} key={persona.persona_id}>{persona.name} · {persona.style}</option>)}
        </select>
        <button className="cmd start" onClick={runPlanner}>Generate TaskSpec</button>
        <button className="cmd" onClick={explain}>Explain Mock Failure</button>
      </div>
      <div className="eventStream">
        <h2>Sandbox Validation</h2>
        <pre>{plan ? JSON.stringify(plan, null, 2) : "TaskSpec must pass schema validation, skill existence, safe tool checks, max retry, and dry-run graph simulation before run."}</pre>
      </div>
      <div className="eventStream">
        <h2>Failure Explanation</h2>
        <pre>{explanation ? JSON.stringify(explanation, null, 2) : "No failure selected."}</pre>
      </div>
    </section>
  );
}

function CompanionOverlay() {
  const [eventCode, setEventCode] = useState("TARGET_LOST");
  const [personaId, setPersonaId] = useState("default_companion");
  const [personas, setPersonas] = useState<PersonaProfile[]>([]);
  const [line, setLine] = useState<Record<string, string> | null>(null);
  const [failure, setFailure] = useState<Record<string, unknown> | null>(null);

  const trigger = async () => {
    const data = await fetch(`${API}/persona/event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_code: eventCode, persona_id: personaId, payload: {} }),
    }).then((r) => r.json());
    setLine(data);
  };

  const whyFailed = async () => {
    const data = await fetch(`${API}/planner/explain_failure`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: "mock", summary: { failure_code: eventCode } }),
    }).then((r) => r.json());
    setFailure(data);
  };

  useEffect(() => {
    fetch(`${API}/persona/profiles`).then((r) => r.json()).then((data) => setPersonas(data.personas ?? [])).catch(() => undefined);
  }, []);

  return (
    <section className="companionPanel">
      <div className="companionAvatar">A</div>
      <div className="bubble">
        <div className="eyebrow">{line?.overlay_state ?? "观察中"}</div>
        <h2>{personas.find((persona) => persona.persona_id === personaId)?.name ?? "Aurora"} Companion</h2>
        <div className={`modePill ${line?.emotion ?? "normal"}`}>{line?.emotion ?? "normal"}</div>
        <p>{line?.message ?? "我会把底层事件翻译成用户能理解的反馈，并保留安全边界。"}</p>
        <select value={personaId} onChange={(event) => setPersonaId(event.target.value)}>
          {personas.map((persona) => <option value={persona.persona_id} key={persona.persona_id}>{persona.name} · {persona.style}</option>)}
        </select>
        <select value={eventCode} onChange={(event) => setEventCode(event.target.value)}>
          {["TARGET_LOST", "NO_TASK_PROGRESS", "RECOVERY_STARTED", "SKILL_TIMEOUT", "TASK_COMPLETE", "FOCUS_LOST", "EMERGENCY_STOP", "DODGE_REFLEX"].map((code) => <option key={code}>{code}</option>)}
        </select>
        <button className="cmd start" onClick={trigger}>Trigger Mock Event</button>
        <button className="cmd" onClick={whyFailed}>Why Failed?</button>
        {failure && <pre>{JSON.stringify(failure, null, 2)}</pre>}
      </div>
      <button className="cmd emergency">Emergency Stop</button>
    </section>
  );
}

function CombatPanel() {
  const [playbook, setPlaybook] = useState<Record<string, unknown> | null>(null);
  const [danger, setDanger] = useState<Record<string, unknown> | null>(null);
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([]);
  const [currentNode, setCurrentNode] = useState("maintain_lock");
  const [jsonView, setJsonView] = useState(false);
  const [showcase, setShowcase] = useState<Record<string, unknown> | null>(null);

  const createPlaybook = async () => {
    const data = await fetch(`${API}/combat/playbook`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal: "安全完成战斗沙盒演示", team_profile: "default_team" }),
    }).then((r) => r.json());
    setPlaybook(data);
    const firstNode = Array.isArray(data?.playbook?.nodes) ? data.playbook.nodes[0]?.node_id : "maintain_lock";
    setCurrentNode(firstNode ?? "maintain_lock");
  };

  const triggerDanger = async () => {
    const data = await fetch(`${API}/combat/danger`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ signals: { generic_warning_area: 1, projectile_approaching: 1, scripted_testbed_danger: 1 }, context_priority: 0.1 }),
    }).then((r) => r.json());
    setDanger(data);
    setCurrentNode(data.level === "HIGH" ? "dodge_if_danger" : "attack_if_safe");
    setHistory((items) => [{ at: new Date().toLocaleTimeString(), ...data }, ...items].slice(0, 6));
  };

  const runShowcase = async () => {
    const data = await fetch(`${API}/showcase/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "dry-run", seconds: 30, persona: "default_companion", provider: "mock" }),
    }).then((r) => r.json());
    setShowcase(data);
  };

  const nodes = (playbook?.playbook as { nodes?: Array<Record<string, unknown>> } | undefined)?.nodes ?? [];
  const score = typeof danger?.danger_score === "number" ? danger.danger_score : 0;
  const dodge = danger?.dodge as Record<string, unknown> | undefined;
  const policy = danger?.dodge_policy as Record<string, unknown> | undefined;

  return (
    <section className="combatPanel">
      <div className="eventStream combatGraph">
        <div className="reportHeader">
          <h2>Combat Playbook</h2>
          <button className="cmd" onClick={() => setJsonView(!jsonView)}>{jsonView ? "Graph" : "JSON"}</button>
        </div>
        <button className="cmd start" onClick={createPlaybook}>Generate Playbook</button>
        {jsonView ? (
          <pre>{playbook ? JSON.stringify(playbook, null, 2) : "Generate a playbook to inspect schema validation."}</pre>
        ) : (
          <div className="nodeGrid">
            {nodes.length ? nodes.map((node) => (
              <div className={node.node_id === currentNode ? "playNode activeNode" : "playNode"} key={String(node.node_id)}>
                <strong>{String(node.node_id)}</strong>
                <span>{String(node.type)} | priority {String(node.priority)}</span>
              </div>
            )) : <div className="empty">Mock/LLM strategist will generate guarded behavior-tree nodes.</div>}
          </div>
        )}
      </div>
      <div className="eventStream combatStatus">
        <h2>Reflex Evasion</h2>
        <button className="cmd emergency" onClick={triggerDanger}>Trigger Danger</button>
        <button className="cmd start" onClick={runShowcase}>Run Showcase Demo</button>
        <div className="dangerMeter">
          <div style={{ width: `${Math.round(score * 100)}%` }} />
        </div>
        <div className="metricGrid2">
          <div><span>DangerScore</span><strong>{score.toFixed(2)}</strong></div>
          <div><span>Current Node</span><strong>{currentNode}</strong></div>
          <div><span>Dodge</span><strong>{String(dodge?.ok ?? "idle")}</strong></div>
          <div><span>Cooldown</span><strong>{String(policy?.cooldown_ms ?? 0)} ms</strong></div>
        </div>
        <p className="empty">{String(danger?.companion_message ?? "Companion will explain danger, dodge, recovery, and completion events.")}</p>
        <pre>{danger ? JSON.stringify(danger, null, 2) : "DangerScore will emit DODGE_REFLEX when high threshold is crossed."}</pre>
        {showcase && <pre>{JSON.stringify(showcase, null, 2)}</pre>}
      </div>
      <div className="eventStream combatHistory">
        <h2>Reflex History</h2>
        {history.length ? history.map((item, index) => (
          <div className="event" key={index}>
            {String(item.at)} | score={Number(item.danger_score ?? 0).toFixed(2)} | level={String(item.level)} | dodge={String((item.dodge as Record<string, unknown> | null)?.ok ?? "none")}
          </div>
        )) : <div className="empty">No danger events yet.</div>}
      </div>
    </section>
  );
}

function ProductChecklist() {
  const [items, setItems] = useState<ChecklistItem[]>([]);
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [log, setLog] = useState("Ready for E2E dry-run.");

  const refresh = async () => {
    const data = await fetch(`${API}/product/checklist`).then((r) => r.json());
    setItems(data.items ?? []);
  };

  const runE2E = async () => {
    setLog("Running dry-run E2E...");
    const data = await fetch(`${API}/product/run_e2e`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "dry-run", seconds: 20, use_mock_llm: true, chaos: "none" }),
    }).then((r) => r.json());
    setItems(data.checklist ?? []);
    setLog(data.ok ? `E2E passed. Report: ${data.report_path}` : `E2E failed: ${data.error}`);
  };

  const latest = async () => {
    const data = await fetch(`${API}/product/latest_report`).then((r) => r.json());
    setReport(data);
  };

  useEffect(() => { refresh().catch(() => undefined); }, []);

  return (
    <section className="plannerPanel">
      <div className="eventStream">
        <h2>Product Demo Checklist</h2>
        <div className="checkGrid">
          {items.map((item) => (
            <div className={item.ok ? "checkItem okItem" : "checkItem warnItem"} key={item.key}>
              <strong>{item.ok ? "OK" : "WAIT"} · {item.label}</strong>
              <span>{item.detail}</span>
            </div>
          ))}
        </div>
        <button className="cmd start" onClick={runE2E}>Run Dry-run E2E</button>
        <button className="cmd" onClick={refresh}>Refresh Checklist</button>
        <button className="cmd" onClick={latest}>Latest Report</button>
      </div>
      <div className="eventStream">
        <h2>Run Result</h2>
        <pre>{report ? JSON.stringify(report, null, 2) : log}</pre>
      </div>
    </section>
  );
}

function demoSkillPayload() {
  return {
    skill_id: "gui_demo_skill",
    name: "GUI Demo Skill",
    type: "ui",
    version: 1,
    metadata: { source: "gui" },
    environment_profile: "default_1920x1080",
    preconditions: ["require_focus"],
    steps: [
      { step_id: "wait_started", type: "wait_visual_trigger", timeout_ms: 1000, interruptible: true, params: { trigger: "action_started", chunk_ms: 100 } },
      { step_id: "fallback", type: "fallback_basic_loop", interruptible: true, params: {} },
    ],
    visual_triggers: { action_started: { type: "target_color_green" } },
    success_criteria: ["visual_action_completed"],
    failure_policy: { max_retries: 1, fallback: "pause_and_reacquire" },
    cleanup: [{ type: "release_all" }],
    safety: { dry_run_default: true, interruptible: true, require_focus: true, max_duration_ms: 3000 },
  };
}

function StatusCard({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return <div className="statusCard"><span>{label}</span><strong className={ok ? "ok" : "warn"}>{value}</strong></div>;
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return <div className="metric">{icon}<span>{label}</span><strong>{value}</strong></div>;
}

function pageTitle(page: Page) {
  return {
    dashboard: "Dashboard",
    monitor: "Run Monitor",
    reports: "Reports",
    settings: "Settings",
    calibration: "Calibration",
    skills: "Skill Library",
    planner: "Task Planner",
    companion: "Companion",
    combat: "Combat",
    checklist: "Product Demo",
  }[page];
}

createRoot(document.getElementById("root")!).render(<App />);
