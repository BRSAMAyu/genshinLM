import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity, AlertTriangle, BookOpen, Bot, ChevronsLeft, ChevronsRight,
  ClipboardCheck, Gauge, Library, Pause, Play, Radar, RotateCw,
  Settings, ShieldCheck, Square, WandSparkles, CheckCircle2, XCircle,
} from "lucide-react";
import "./styles/components.css";
import { I18nContext, LangContext, dicts, useI18n, useLang } from "./i18n";
import type { Lang } from "./i18n";

// ─── Types ───

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
  title: string; pid: number; handle: number;
  rect: { left: number; top: number; right: number; bottom: number; width: number; height: number };
  focused: boolean; visible: boolean;
};

type RoiDraft = {
  name: string; mode: "relative" | "anchor";
  anchor: "top-left" | "top-right" | "bottom-left" | "bottom-right" | "center";
  rect: { x: number; y: number; w: number; h: number };
};

type ModelStatus = {
  detector_backend: string; model_path: string | null; model_exists: boolean;
  ultralytics_available: boolean; tracker: string; tracker_available: boolean;
  device: string; half: boolean;
};

type SkillSummary = { skill_id: string; name: string; type: string; version: number; archived?: boolean; };
type ChecklistItem = { key: string; label: string; ok: boolean; detail: string; };
type PersonaProfile = { persona_id: string; name: string; style: string; tone: string; };

const API = "http://127.0.0.1:8765";
const WS = "ws://127.0.0.1:8765/ws/state";

const fallbackState: AgentState = {
  mode: "STOPPED", current_node: "INIT", current_skill: null, target_state: "NONE",
  progress: 0, frustration: 0, input_backend: "console", focus_status: "DISCONNECTED",
  active_interrupt: null,
  runtime_health: { healthy: true, input_worker_alive: false, telemetry_ok: true, release_all_called: true, updated_at: 0 },
  input_released: true, telemetry_ok: true, latest_run_id: null, updated_at: 0,
};

// ─── App Shell ───

function App() {
  const [lang, setLang] = useState<Lang>("zh");
  const dict = dicts[lang];
  const [state, setState] = useState<AgentState>(fallbackState);
  const [page, setPage] = useState<Page>("dashboard");
  const [events, setEvents] = useState<string[]>([]);
  const [report, setReport] = useState<string>("");
  const [connected, setConnected] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  useEffect(() => {
    fetch(`${API}/state`).then((r) => r.json()).then(setState).catch(() => {});
    const socket = new WebSocket(WS);
    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onmessage = (msg) => {
      const next = JSON.parse(msg.data) as AgentState;
      setState(next);
      setEvents((items) => [
        `${new Date().toLocaleTimeString()} ${next.mode} ${next.current_node} ${next.target_state}`,
        ...items.slice(0, 50),
      ]);
    };
    return () => socket.close();
  }, []);

  useEffect(() => {
    if (page !== "reports") return;
    fetch(`${API}/runs/latest`).then((r) => r.json()).then((d) => setReport(d.report_markdown ?? "")).catch(() => setReport(""));
  }, [page]);

  const command = async (path: string) => {
    const r = await fetch(`${API}${path}`, { method: "POST" });
    const p = await r.json();
    setState(p.state);
  };

  const modeClass = state.mode.toLowerCase().replace("_", "_");

  return (
    <LangContext.Provider value={{ lang, setLang }}>
      <I18nContext.Provider value={dict}>
        <div className="shell">
          <Sidebar page={page} setPage={setPage} connected={connected} collapsed={sidebarCollapsed} setCollapsed={setSidebarCollapsed} />
          <main className="main">
            <div className="topbar">
              <div className="topbar-left">
                <div className="eyebrow">{connected ? dict.connected : dict.offline}</div>
                <h1>{pageTitle(dict, page)}</h1>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <LangToggle />
                <div className={`modePill ${modeClass}`}>{modeLabel(dict, state.mode)}</div>
              </div>
            </div>
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
      </I18nContext.Provider>
    </LangContext.Provider>
  );
}

// ─── Lang Toggle ───

function LangToggle() {
  const { lang, setLang } = useLang();
  return (
    <div className="lang-toggle">
      <button className={lang === "zh" ? "active" : ""} onClick={() => setLang("zh")}>中文</button>
      <button className={lang === "en" ? "active" : ""} onClick={() => setLang("en")}>EN</button>
    </div>
  );
}

// ─── Sidebar ───

function Sidebar({ page, setPage, connected, collapsed, setCollapsed }: {
  page: Page; setPage: (p: Page) => void; connected: boolean; collapsed: boolean; setCollapsed: (c: boolean) => void;
}) {
  const t = useI18n();
  const sections = useMemo(() => [
    { label: t.navSection_monitor, items: [
      { id: "dashboard" as Page, icon: <Bot size={16} />, label: t.nav_dashboard },
      { id: "monitor" as Page, icon: <Activity size={16} />, label: t.nav_monitor },
      { id: "reports" as Page, icon: <BookOpen size={16} />, label: t.nav_reports },
    ]},
    { label: t.navSection_configure, items: [
      { id: "calibration" as Page, icon: <Radar size={16} />, label: t.nav_calibration },
      { id: "skills" as Page, icon: <Library size={16} />, label: t.nav_skills },
      { id: "planner" as Page, icon: <WandSparkles size={16} />, label: t.nav_planner },
    ]},
    { label: t.navSection_intelligence, items: [
      { id: "companion" as Page, icon: <Bot size={16} />, label: t.nav_companion },
      { id: "combat" as Page, icon: <Gauge size={16} />, label: t.nav_combat },
    ]},
    { label: t.navSection_system, items: [
      { id: "settings" as Page, icon: <Settings size={16} />, label: t.nav_settings },
      { id: "checklist" as Page, icon: <ShieldCheck size={16} />, label: t.nav_checklist },
    ]},
  ], [t]);

  return (
    <aside className={`sidebar${collapsed ? " collapsed" : ""}`}>
      <div className="brand">
        <div className="brandMark">A</div>
        <div className="brand-text">
          <div className="brandTitle">{t.brandTitle}</div>
          <div className="brandSub">{t.brandSub}</div>
        </div>
      </div>
      {sections.map((sec) => (
        <div className="nav-section" key={sec.label}>
          <div className="nav-section-label">{sec.label}</div>
          {sec.items.map((item) => (
            <button key={item.id} className={`nav-item${page === item.id ? " active" : ""}`} onClick={() => setPage(item.id)}>
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
            </button>
          ))}
        </div>
      ))}
      <div className="sidebar-footer">
        <span className={`sidebar-footer-dot ${connected ? "ok" : "off"}`} />
        <span className="sidebar-footer-text">{connected ? t.connected : t.offline}</span>
      </div>
      <button className="sidebar-toggle" onClick={() => setCollapsed(!collapsed)}>
        {collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
      </button>
    </aside>
  );
}

// ─── Dashboard ───

function Dashboard({ state, command, navigate }: { state: AgentState; command: (p: string) => Promise<void>; navigate: (p: Page) => void }) {
  const t = useI18n();
  const [diagnostics, setDiagnostics] = useState<Array<{ key: string; label: string; status: string; detail: string }> | null>(null);
  const runDiag = async () => {
    const d = await fetch(`${API}/diagnostics/run`, { method: "POST" }).then((r) => r.json());
    setDiagnostics(d.checks ?? null);
  };

  return (
    <div className="grid-auto">
      {/* Status bar */}
      <div className="card" style={{ display: "flex", alignItems: "center", gap: 16, padding: "16px 20px" }}>
        <div className={`status-dot ${state.mode === "RUNNING" ? "running" : state.mode === "EMERGENCY_STOPPED" ? "error" : "neutral"}`} style={{ width: 10, height: 10 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>{modeLabel(t, state.mode)}</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            {state.current_node} · {state.current_skill ?? t.dash_no_skill}
          </div>
        </div>
        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{t.dash_dryrun}</div>
      </div>

      {/* Commands */}
      <div className="card">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          <button className="btn btn-primary" onClick={() => command("/agent/start")}><Play size={15} />{t.btn_start}</button>
          <button className="btn" onClick={() => command("/agent/pause")}><Pause size={15} />{t.btn_pause}</button>
          <button className="btn" onClick={() => command("/agent/resume")}><RotateCw size={15} />{t.btn_resume}</button>
          <button className="btn" onClick={() => command("/agent/stop")}><Square size={15} />{t.btn_stop}</button>
          <button className="btn btn-danger" style={{ marginLeft: "auto" }} onClick={() => command("/agent/emergency_stop")}>
            <AlertTriangle size={15} />{t.btn_emergency}
          </button>
        </div>
      </div>

      {/* Health */}
      <div className="grid-4">
        <HealthItem label={t.label_focus} value={state.focus_status === "DRY_RUN" ? t.val_dryrun : state.focus_status} ok={state.focus_status === "DRY_RUN"} />
        <HealthItem label={t.label_input} value={state.input_released ? t.val_released : t.val_held} ok={state.input_released} />
        <HealthItem label={t.label_telemetry} value={state.telemetry_ok ? t.val_streaming : t.val_backpressure} ok={state.telemetry_ok} />
        <HealthItem label={t.label_health} value={state.runtime_health.healthy ? t.val_healthy : t.val_attention} ok={state.runtime_health.healthy} />
      </div>

      {/* Quick actions */}
      <div className="card" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button className="btn btn-primary" onClick={() => command("/agent/start")}><Play size={15} />{t.btn_start_service}</button>
        <button className="btn" onClick={() => runDiag()}><ShieldCheck size={15} />{t.btn_run_diag}</button>
        <button className="btn" onClick={() => navigate("calibration")}><Radar size={15} />{t.btn_open_calib}</button>
        <button className="btn" onClick={() => navigate("skills")}><Library size={15} />{t.btn_open_skills}</button>
      </div>

      {/* Diagnostics */}
      {diagnostics && (
        <div className="card">
          <div className="card-header"><h2>{t.btn_run_diag}</h2></div>
          <div className="grid-3">
            {diagnostics.map((c) => (
              <div key={c.key} className={`check-item ${c.status === "ok" ? "ok" : "warn"}`}>
                <span className="check-icon">{c.status === "ok" ? <CheckCircle2 size={16} style={{ color: "var(--status-ok)" }} /> : <XCircle size={16} style={{ color: "var(--status-warn)" }} />}</span>
                <div className="check-detail">
                  <span className="check-label">{c.key}</span>
                  <span className="check-desc">{c.detail}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Run Monitor ───

function RunMonitor({ state, events }: { state: AgentState; events: string[] }) {
  const t = useI18n();
  return (
    <div className="grid-auto">
      <div className="grid-4">
        <div className="metric-card">
          <span className="metric-label"><Gauge size={14} />{t.metric_progress}</span>
          <span className="metric-value">{Math.round(state.progress * 100)}%</span>
        </div>
        <div className="metric-card">
          <span className="metric-label"><AlertTriangle size={14} />{t.metric_frustration}</span>
          <span className="metric-value">{state.frustration.toFixed(1)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label"><Radar size={14} />{t.metric_target}</span>
          <span className="metric-value">{state.target_state}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label"><ShieldCheck size={14} />{t.metric_interrupt}</span>
          <span className="metric-value">{state.active_interrupt ? String(state.active_interrupt.code) : t.metric_none}</span>
        </div>
      </div>
      <div className="card">
        <div className="card-header">
          <h2>{t.header_events}</h2>
        </div>
        <div className="event-stream">
          {events.length ? events.map((ev, i) => {
            const parts = ev.split(" ");
            const mode = parts[1] ?? "";
            const modeCls = mode.includes("RUNNING") ? "running" : mode.includes("PAUSED") ? "paused" : mode.includes("EMERGENCY") ? "emergency" : "stopped";
            return (
              <div className="event-row" key={i}>
                <span className="event-time">{parts[0]}</span>
                <span className={`event-mode ${modeCls}`}>{mode}</span>
                <span className="event-detail">{parts.slice(2).join(" ")}</span>
              </div>
            );
          }) : <div className="empty">{t.empty_events}</div>}
        </div>
      </div>
    </div>
  );
}

// ─── Reports ───

function Reports({ report, runId }: { report: string; runId: string | null }) {
  const t = useI18n();
  const [active, setActive] = useState(report);
  const [title, setTitle] = useState(runId ?? t.latest_run);
  useEffect(() => setActive(report), [report]);
  const load = async (path: string, label: string) => {
    const d = await fetch(`${API}${path}`).then((r) => r.json());
    setTitle(d.run_id ?? label);
    setActive(d.report_markdown ?? "");
  };
  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="eyebrow">{t.header_reports}</div>
          <h2>{title}</h2>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn" onClick={() => load("/runs/latest", t.title_kernel)}>{t.btn_kernel}</button>
          <button className="btn" onClick={() => load("/product/latest_report", t.title_product)}>{t.btn_product}</button>
          <button className="btn btn-primary" onClick={() => load("/showcase/latest_report", t.title_showcase)}>{t.btn_showcase}</button>
        </div>
      </div>
      {active ? <pre>{active}</pre> : <div className="empty">{t.empty_report}</div>}
    </div>
  );
}

// ─── Settings ───

function SettingsPage({ state }: { state: AgentState }) {
  const t = useI18n();
  return (
    <div className="grid-2">
      <HealthItem label={t.label_input_backend} value={state.input_backend} ok={state.input_backend === "console"} />
      <HealthItem label={t.label_real_input} value={t.val_disabled_default} ok />
      <HealthItem label={t.label_safe_window} value={t.val_required_physical} ok />
      <HealthItem label={t.label_f9_stop} value={t.val_enabled_runners} ok />
    </div>
  );
}

// ─── Calibration Wizard ───

function CalibrationWizard() {
  const t = useI18n();
  const [step, setStep] = useState(1);
  const [runMode, setRunMode] = useState(t.mode_sandbox);
  const [windows, setWindows] = useState<WindowSummary[]>([]);
  const [selected, setSelected] = useState<WindowSummary | null>(null);
  const [snapshotVer, setSnapshotVer] = useState(0);
  const [roiName, setRoiName] = useState("main_view");
  const [roiMode, setRoiMode] = useState<"relative" | "anchor">("relative");
  const [anchor, setAnchor] = useState<RoiDraft["anchor"]>("top-right");
  const [rois, setRois] = useState<RoiDraft[]>([]);
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [draftRect, setDraftRect] = useState<RoiDraft["rect"] | null>(null);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [benchmark, setBenchmark] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState(t.msg_choose_mode);

  const refreshWindows = async () => {
    const d = await fetch(`${API}/windows`).then((r) => r.json());
    setWindows(d.windows ?? []);
    setMessage(d.windows?.length ? t.msg_select_window : t.msg_no_window);
  };
  const selectWindow = async (w: WindowSummary) => {
    const d = await fetch(`${API}/window/select`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ handle: w.handle }) }).then((r) => r.json());
    if (d.detail) { setMessage(d.detail); return; }
    setSelected(d.window); setSnapshotVer(Date.now());
    setMessage(t.msg_window_selected);
  };
  const startDrag = (e: React.MouseEvent<HTMLDivElement>) => {
    const b = e.currentTarget.getBoundingClientRect();
    setDragStart({ x: (e.clientX - b.left) / b.width, y: (e.clientY - b.top) / b.height });
    setDraftRect({ x: (e.clientX - b.left) / b.width, y: (e.clientY - b.top) / b.height, w: 0, h: 0 });
  };
  const updateDrag = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!dragStart) return;
    const b = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - b.left) / b.width, y = (e.clientY - b.top) / b.height;
    setDraftRect({ x: Math.min(dragStart.x, x), y: Math.min(dragStart.y, y), w: Math.abs(x - dragStart.x), h: Math.abs(y - dragStart.y) });
  };
  const endDrag = () => {
    if (!draftRect || draftRect.w < 0.01 || draftRect.h < 0.01) { setDragStart(null); return; }
    setRois((items) => [...items.filter((i) => i.name !== roiName), { name: roiName, mode: roiMode, anchor, rect: draftRect }]);
    setDragStart(null); setDraftRect(null);
    setMessage(t.msg_roi_captured);
  };
  const saveProfile = async () => {
    if (!selected) { setMessage(t.msg_select_before_save); return; }
    const pid = `profile_${selected.rect.width}x${selected.rect.height}`;
    await fetch(`${API}/calibration/profile`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile: { profile_id: pid, window_title: selected.title, source_resolution: [selected.rect.width, selected.rect.height], normalized_resolution: [1280, 720], rois: Object.fromEntries(rois.map((r) => [r.name, { mode: r.mode, x: r.rect.x, y: r.rect.y, w: r.rect.w, h: r.rect.h }])) }, activate: true }) }).then((r) => r.json());
    const tested = await fetch(`${API}/calibration/test`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile_id: pid }) }).then((r) => r.json());
    setMessage(tested.ok ? t.msg_profile_saved : `${t.msg_profile_review} ${tested.errors?.join(", ")}`);
  };

  useEffect(() => { refreshWindows().catch(() => setMessage(t.msg_cant_load_windows)); fetch(`${API}/models/status`).then((r) => r.json()).then(setModelStatus).catch(() => {}); }, []);

  const progress = Math.round((step / 6) * 100);

  return (
    <div className="grid-auto">
      <div className="card">
        <div style={{ marginBottom: 12 }}>
          <div className="eyebrow">{t.label_first_run}</div>
          <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>{t.header_calib}</h2>
          <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>{message}</p>
        </div>
        <div className="progress-track"><div className="progress-fill" style={{ width: `${progress}%` }} /></div>
      </div>
      <div className="wizard-steps">
        {[1, 2, 3, 4, 5, 6].map((s) => (
          <button key={s} className={`wizard-step${step === s ? " active" : ""}`} onClick={() => setStep(s)}>{t.step} {s}</button>
        ))}
      </div>
      <div className="card" style={{ minHeight: 360 }}>
        {step === 1 && (
          <div className="grid-4">
            {[t.mode_sandbox, t.mode_qa, t.mode_analysis, t.mode_dryrun_only].map((m) => (
              <button key={m} className="card" style={{ cursor: "pointer", textAlign: "left", display: "flex", flexDirection: "column", gap: 8 }}
                onClick={() => setRunMode(m)}>
                <strong style={{ fontSize: 14 }}>{m}</strong>
                <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{m === t.mode_dryrun_only ? t.desc_dryrun_only : t.desc_guided}</span>
              </button>
            ))}
          </div>
        )}
        {step === 2 && (
          <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: 16 }}>
            <div>
              <button className="btn" style={{ marginBottom: 12 }} onClick={refreshWindows}>{t.btn_refresh_windows}</button>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 480, overflow: "auto" }}>
                {windows.map((w) => (
                  <button key={w.handle} className={`window-row${selected?.handle === w.handle ? " active" : ""}`} onClick={() => selectWindow(w)}>
                    <span className="window-row-title">{w.title}</span>
                    <span className="window-row-meta">{w.rect.width}x{w.rect.height} pid={w.pid} {w.focused ? t.val_focused : ""}</span>
                  </button>
                ))}
              </div>
            </div>
            <div className="snapshot-box">
              {selected ? <img src={`${API}/capture/snapshot?v=${snapshotVer}`} /> : <div className="empty">{t.empty_select_window}</div>}
            </div>
          </div>
        )}
        {step === 3 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }} className="select-wrap">
              <select value={roiName} onChange={(e) => setRoiName(e.target.value)}>
                {["main_view", "target_area", "minimap", "skill_bar", "status_area", "dialog_area", "interaction_prompt_area"].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
              <select value={roiMode} onChange={(e) => setRoiMode(e.target.value as "relative" | "anchor")}>
                <option value="relative">{t.mode_relative}</option>
                <option value="anchor">{t.mode_anchor}</option>
              </select>
              <select value={anchor} onChange={(e) => setAnchor(e.target.value as RoiDraft["anchor"])}>
                {["top-left", "top-right", "bottom-left", "bottom-right", "center"].map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
            <div className="snapshot-box selectable" onMouseDown={startDrag} onMouseMove={updateDrag} onMouseUp={endDrag}>
              {selected ? <img src={`${API}/capture/snapshot?v=${snapshotVer}`} /> : <div className="empty">{t.empty_select_window}</div>}
              {[...rois.map((r) => r.rect), ...(draftRect ? [draftRect] : [])].map((rect, i) => (
                <div key={i} className="roi-rect" style={{ left: `${rect.x * 100}%`, top: `${rect.y * 100}%`, width: `${rect.w * 100}%`, height: `${rect.h * 100}%` }} />
              ))}
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {rois.map((r) => <span key={r.name} style={{ fontSize: 12, color: "var(--text-secondary)", padding: "4px 8px", border: "1px solid var(--border-default)", borderRadius: 6 }}>{r.name}: {r.mode}</span>)}
            </div>
          </div>
        )}
        {step === 4 && (
          <div className="grid-auto" style={{ gap: 12 }}>
            <div className="grid-4">
              <HealthItem label={t.label_detector} value={modelStatus?.detector_backend ?? "unknown"} ok />
              <HealthItem label={t.label_model_file} value={modelStatus?.model_exists ? t.val_found : t.val_missing} ok={!!modelStatus?.model_exists} />
              <HealthItem label={t.label_ultralytics} value={modelStatus?.ultralytics_available ? t.val_available : t.val_unavailable} ok={!!modelStatus?.ultralytics_available} />
              <HealthItem label={t.label_tracker} value={`${modelStatus?.tracker ?? "unknown"}`} ok={!!modelStatus?.tracker_available} />
            </div>
            <button className="btn btn-primary" onClick={async () => setBenchmark(await fetch(`${API}/models/benchmark`, { method: "POST" }).then((r) => r.json()))}>{t.btn_benchmark}</button>
            <pre>{benchmark ? JSON.stringify(benchmark, null, 2) : t.desc_benchmark}</pre>
          </div>
        )}
        {step === 5 && (
          <div className="grid-2">
            <HealthItem label={t.label_calib_input} value={t.val_dryrun_console} ok />
            <HealthItem label={t.label_calib_f9} value={t.val_enabled} ok />
            <HealthItem label={t.label_focus_protect} value={t.val_required_safewin} ok />
            <HealthItem label={t.label_release_test} value={t.val_via_emergency} ok />
          </div>
        )}
        {step === 6 && (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, padding: 40 }}>
            <h2>{t.header_save_profile}</h2>
            <p style={{ color: "var(--text-secondary)", fontSize: 13, textAlign: "center" }}>{t.desc_save_profile}</p>
            <button className="btn btn-primary" onClick={saveProfile}>{t.btn_save_profile}</button>
          </div>
        )}
      </div>
      <div className="wizard-footer">
        <button className="btn" onClick={() => setStep(Math.max(1, step - 1))}>{t.btn_back}</button>
        <button className="btn btn-primary" onClick={() => setStep(Math.min(6, step + 1))}>{t.btn_next}</button>
      </div>
    </div>
  );
}

// ─── Skill Library ───

function SkillLibrary() {
  const t = useI18n();
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);
  const [session, setSession] = useState<Record<string, unknown> | null>(null);
  const [log, setLog] = useState(t.log_ready);

  const refresh = async () => { const d = await fetch(`${API}/skills`).then((r) => r.json()); setSkills(d.skills ?? []); };
  const startRec = async () => { const d = await fetch(`${API}/skills/record/start`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ backend: "mock" }) }).then((r) => r.json()); setSession(d.session ?? null); setLog(d.message); };
  const stopRec = async () => { const d = await fetch(`${API}/skills/record/stop`, { method: "POST" }).then((r) => r.json()); setDraft(d.draft); setSession(null); setLog(t.log_draft_generated); };
  const addMarker = async () => { await fetch(`${API}/skills/record/marker`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ marker: "manual_checkpoint" }) }); setLog(t.log_marker_added); };
  const addEvent = async () => { const d = await fetch(`${API}/skills/record/event`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ event_type: "mouse_click", payload: { button: "left" }, target_state: "TRACKED", focus_state: "FOCUSED", visual_triggers: { target_visible: true } }) }).then((r) => r.json()); setSession(d.session ?? null); setLog(t.log_event_captured); };
  const saveDraft = async () => { const d = await fetch(`${API}/skills/record/save`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: "Recorded Test Window Skill" }) }).then((r) => r.json()); setSelected(d.skill_id ?? null); setLog(d.skill_id ? t.log_saved.replace("{id}", d.skill_id).replace("{version}", String(d.version)) : "Error"); refresh(); };
  const saveDemo = async () => { const d = await fetch(`${API}/skills`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(demoSkillPayload()) }).then((r) => r.json()); setSelected(d.skill_id ?? null); setLog(d.skill_id ? t.log_saved.replace("{id}", d.skill_id).replace("{version}", String(d.version)) : "Error"); refresh(); };
  const validate = async () => { if (!selected) return; const d = await fetch(`${API}/skills/${selected}/validate`, { method: "POST" }).then((r) => r.json()); setLog(d.ok ? t.log_validated : d.errors.join("\n")); };
  const dryRun = async () => { if (!selected) return; const d = await fetch(`${API}/skills/${selected}/dry_run`, { method: "POST" }).then((r) => r.json()); setLog((d.result?.payload?.logs ?? []).join("\n") || JSON.stringify(d, null, 2)); };
  const replay = async () => { if (!selected) return; const d = await fetch(`${API}/skills/${selected}/replay`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "dry-run", confirm: false }) }).then((r) => r.json()); setLog((d.result?.payload?.logs ?? []).join("\n") || JSON.stringify(d, null, 2)); };

  useEffect(() => { refresh().catch(() => {}); }, []);

  return (
    <div className="editor-shell">
      <div className="editor-aside">
        <button className="btn btn-primary btn-full" onClick={startRec}>{t.btn_start_rec}</button>
        <button className="btn btn-full" onClick={addEvent}>{t.btn_capture_event}</button>
        <button className="btn btn-full" onClick={addMarker}>{t.btn_marker}</button>
        <button className="btn btn-full" onClick={stopRec}>{t.btn_stop_rec}</button>
        <button className="btn btn-primary btn-full" onClick={saveDraft}>{t.btn_save_draft}</button>
        <button className="btn btn-full" onClick={saveDemo}>{t.btn_save_demo}</button>
        {skills.map((s) => (
          <button key={s.skill_id} className={`window-row${selected === s.skill_id ? " active" : ""}`} onClick={() => setSelected(s.skill_id)}>
            <span className="window-row-title">{s.name}</span>
            <span className="window-row-meta">{s.type} v{s.version}</span>
          </button>
        ))}
      </div>
      <div className="editor-main">
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>{t.header_timeline}</h2>
        {draft ? <pre>{JSON.stringify(draft, null, 2)}</pre> : session ? <pre>{JSON.stringify(session, null, 2)}</pre> : <div className="empty">{t.empty_skill}</div>}
      </div>
      <div className="editor-aside">
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>{t.header_properties}</h2>
        <button className="btn btn-full" onClick={validate}>{t.btn_validate}</button>
        <button className="btn btn-primary btn-full" onClick={dryRun}>{t.btn_dryrun}</button>
        <button className="btn btn-full" onClick={replay}>{t.btn_replay}</button>
        <pre style={{ fontSize: 11 }}>{log}</pre>
      </div>
    </div>
  );
}

// ─── Task Planner ───

function TaskPlanner() {
  const t = useI18n();
  const [goal, setGoal] = useState(t.default_goal);
  const [provider, setProvider] = useState("mock");
  const [personaId, setPersonaId] = useState("default_companion");
  const [personas, setPersonas] = useState<PersonaProfile[]>([]);
  const [plan, setPlan] = useState<Record<string, unknown> | null>(null);
  const [explanation, setExplanation] = useState<Record<string, unknown> | null>(null);

  useEffect(() => { fetch(`${API}/persona/profiles`).then((r) => r.json()).then((d) => setPersonas(d.personas ?? [])).catch(() => {}); }, []);

  return (
    <div className="grid-2">
      <div className="card">
        <div className="card-header"><h2>{t.header_goal}</h2></div>
        <textarea className="textarea" value={goal} onChange={(e) => setGoal(e.target.value)} />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }} className="select-wrap">
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="mock">mock</option><option value="glm">glm</option><option value="minimax">minimax</option>
          </select>
          <select value={personaId} onChange={(e) => setPersonaId(e.target.value)}>
            {personas.map((p) => <option value={p.persona_id} key={p.persona_id}>{p.name} · {p.style}</option>)}
          </select>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button className="btn btn-primary" onClick={async () => setPlan(await fetch(`${API}/planner/task`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ goal, provider, persona_id: personaId }) }).then((r) => r.json()))}>{t.btn_generate}</button>
          <button className="btn" onClick={async () => setExplanation(await fetch(`${API}/planner/explain_failure`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ summary: { failure_code: "TARGET_LOST" }, provider }) }).then((r) => r.json()))}>{t.btn_explain_fail}</button>
        </div>
      </div>
      <div className="card">
        <div className="card-header"><h2>{t.header_sandbox}</h2></div>
        <pre>{plan ? JSON.stringify(plan, null, 2) : t.empty_plan}</pre>
      </div>
      <div className="card" style={{ gridColumn: "1 / -1" }}>
        <div className="card-header"><h2>{t.header_failure}</h2></div>
        <pre>{explanation ? JSON.stringify(explanation, null, 2) : t.empty_failure}</pre>
      </div>
    </div>
  );
}

// ─── Companion ───

function CompanionOverlay() {
  const t = useI18n();
  const [eventCode, setEventCode] = useState("TARGET_LOST");
  const [personaId, setPersonaId] = useState("default_companion");
  const [personas, setPersonas] = useState<PersonaProfile[]>([]);
  const [line, setLine] = useState<Record<string, string> | null>(null);
  const [failure, setFailure] = useState<Record<string, unknown> | null>(null);
  const [history, setHistory] = useState<Array<{ time: string; event: string; message: string }>>([]);
  const [typing, setTyping] = useState(false);

  useEffect(() => { fetch(`${API}/persona/profiles`).then((r) => r.json()).then((d) => setPersonas(d.personas ?? [])).catch(() => {}); }, []);

  const trigger = async () => {
    setTyping(true);
    const d = await fetch(`${API}/persona/event`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ event_code: eventCode, persona_id: personaId, payload: {} }) }).then((r) => r.json());
    setLine(d);
    setTyping(false);
    setHistory((h) => [{ time: new Date().toLocaleTimeString(), event: eventCode, message: d.message ?? "" }, ...h].slice(0, 20));
  };

  const emotion = line?.emotion ?? "normal";
  const personaName = personas.find((p) => p.persona_id === personaId)?.name ?? "Aurora";

  return (
    <div className="grid-auto" style={{ gap: 20 }}>
      <div className="card" style={{ display: "flex", gap: 24, alignItems: "flex-start", padding: 28 }}>
        <div className={`companion-avatar ${typing ? "thinking" : emotion}`} style={{ marginTop: 8 }}>A</div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="eyebrow">{line?.overlay_state ?? "观察中"}</span>
            <span className={`emotion-pill ${emotion}`}>{emotion}</span>
          </div>
          <h2 style={{ fontSize: 20, fontWeight: 700 }}>{t.header_companion.replace("{name}", personaName)}</h2>
          <div className={`bubble${typing ? " bubble-typing" : ""}`}>
            <p>{typing ? "" : (line?.message ?? "我会把底层事件翻译成用户能理解的反馈，并保留安全边界。")}</p>
          </div>
        </div>
      </div>

      <div className="card" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <div className="select-wrap" style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <select value={personaId} onChange={(e) => setPersonaId(e.target.value)}>
            {personas.map((p) => <option value={p.persona_id} key={p.persona_id}>{p.name} · {p.style}</option>)}
          </select>
          <select value={eventCode} onChange={(e) => setEventCode(e.target.value)}>
            {["TARGET_LOST", "NO_TASK_PROGRESS", "RECOVERY_STARTED", "SKILL_TIMEOUT", "TASK_COMPLETE", "FOCUS_LOST", "EMERGENCY_STOP", "DODGE_REFLEX"].map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
        <button className="btn btn-primary" onClick={trigger}>{t.btn_trigger_event}</button>
        <button className="btn" onClick={async () => setFailure(await fetch(`${API}/planner/explain_failure`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ provider: "mock", summary: { failure_code: eventCode } }) }).then((r) => r.json()))}>{t.btn_why_failed}</button>
      </div>

      {history.length > 0 && (
        <div className="card">
          <div className="card-header"><h2>Event History</h2></div>
          <div className="event-stream">
            {history.map((h, i) => (
              <div className="event-row" key={i}>
                <span className="event-time">{h.time}</span>
                <span className="event-mode">{h.event}</span>
                <span className="event-detail">{h.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {failure && <div className="card"><pre>{JSON.stringify(failure, null, 2)}</pre></div>}

      <button className="btn btn-danger btn-full" style={{ padding: 16 }}>
        <AlertTriangle size={16} />{t.btn_emergency}
      </button>
    </div>
  );
}

// ─── Combat ───

function CombatPanel() {
  const t = useI18n();
  const [playbook, setPlaybook] = useState<Record<string, unknown> | null>(null);
  const [danger, setDanger] = useState<Record<string, unknown> | null>(null);
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([]);
  const [currentNode, setCurrentNode] = useState("maintain_lock");
  const [jsonView, setJsonView] = useState(false);
  const [showcase, setShowcase] = useState<Record<string, unknown> | null>(null);

  const nodes = (playbook?.playbook as { nodes?: Array<Record<string, unknown>> } | undefined)?.nodes ?? [];
  const score = typeof danger?.danger_score === "number" ? danger.danger_score : 0;
  const dodge = danger?.dodge as Record<string, unknown> | undefined;
  const policy = danger?.dodge_policy as Record<string, unknown> | undefined;

  return (
    <div className="grid-auto">
      <div className="grid-2">
        <div className="card">
          <div className="card-header">
            <h2>{t.header_playbook}</h2>
            <button className="btn" onClick={() => setJsonView(!jsonView)}>{jsonView ? t.btn_graph : t.btn_json}</button>
          </div>
          <button className="btn btn-primary" style={{ marginBottom: 12 }} onClick={async () => {
            const d = await fetch(`${API}/combat/playbook`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ goal: "安全完成战斗沙盒演示", team_profile: "default_team" }) }).then((r) => r.json());
            setPlaybook(d);
            setCurrentNode(Array.isArray(d?.playbook?.nodes) ? String(d.playbook.nodes[0]?.node_id ?? "maintain_lock") : "maintain_lock");
          }}>{t.btn_generate_playbook}</button>
          {jsonView ? <pre>{playbook ? JSON.stringify(playbook, null, 2) : t.empty_playbook}</pre> : (
            <div className="grid-2" style={{ gap: 8 }}>
              {nodes.length ? nodes.map((n) => (
                <div key={String(n.node_id)} className={`combat-node${n.node_id === currentNode ? " active" : ""}`}>
                  <span className="combat-node-label">{String(n.node_id)}</span>
                  <span className="combat-node-meta">{String(n.type)} | priority {String(n.priority)}</span>
                </div>
              )) : <div className="empty" style={{ gridColumn: "1 / -1" }}>{t.empty_nodes}</div>}
            </div>
          )}
        </div>
        <div className="card">
          <div className="card-header"><h2>{t.header_reflex}</h2></div>
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <button className="btn btn-danger" onClick={async () => {
              const d = await fetch(`${API}/combat/danger`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ signals: { generic_warning_area: 1, projectile_approaching: 1, scripted_testbed_danger: 1 }, context_priority: 0.1 }) }).then((r) => r.json());
              setDanger(d); setCurrentNode(d.level === "HIGH" ? "dodge_if_danger" : "attack_if_safe");
              setHistory((h) => [{ at: new Date().toLocaleTimeString(), ...d }, ...h].slice(0, 6));
            }}>{t.btn_trigger_danger}</button>
            <button className="btn btn-primary" onClick={async () => setShowcase(await fetch(`${API}/showcase/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "dry-run", seconds: 30, persona: "default_companion", provider: "mock" }) }).then((r) => r.json()))}>{t.btn_run_showcase}</button>
          </div>
          <div className="danger-meter">
            <div className="danger-meter-fill" style={{ width: `${Math.round(score * 100)}%` }} />
            <span className="danger-meter-label">{Math.round(score * 100)}%</span>
          </div>
          <div className="grid-2" style={{ gap: 8 }}>
            <div className="metric-card"><span className="metric-label">{t.metric_danger_score}</span><span className="metric-value">{score.toFixed(2)}</span></div>
            <div className="metric-card"><span className="metric-label">{t.metric_current_node}</span><span className="metric-value" style={{ fontSize: 14 }}>{currentNode}</span></div>
            <div className="metric-card"><span className="metric-label">{t.metric_dodge}</span><span className="metric-value">{String(dodge?.ok ?? "idle")}</span></div>
            <div className="metric-card"><span className="metric-label">{t.metric_cooldown}</span><span className="metric-value">{String(policy?.cooldown_ms ?? 0)} ms</span></div>
          </div>
          <div style={{ marginTop: 8 }}>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", fontStyle: "italic" }}>{String(danger?.companion_message ?? t.empty_companion_combat)}</p>
          </div>
          {danger && <pre style={{ marginTop: 8 }}>{JSON.stringify(danger, null, 2)}</pre>}
          {showcase && <pre>{JSON.stringify(showcase, null, 2)}</pre>}
        </div>
      </div>
      <div className="card">
        <div className="card-header"><h2>{t.header_history}</h2></div>
        {history.length ? (
          <div className="event-stream">
            {history.map((item, i) => (
              <div className="event-row" key={i}>
                <span className="event-time">{String(item.at)}</span>
                <span className="event-mode">score={Number(item.danger_score ?? 0).toFixed(2)}</span>
                <span className="event-detail">level={String(item.level)} dodge={String((item.dodge as Record<string, unknown> | null)?.ok ?? "none")}</span>
              </div>
            ))}
          </div>
        ) : <div className="empty">{t.empty_no_danger}</div>}
      </div>
    </div>
  );
}

// ─── Product Checklist ───

function ProductChecklist() {
  const t = useI18n();
  const [items, setItems] = useState<ChecklistItem[]>([]);
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [log, setLog] = useState(t.log_e2e_ready);

  useEffect(() => { fetch(`${API}/product/checklist`).then((r) => r.json()).then((d) => setItems(d.items ?? [])).catch(() => {}); }, []);

  return (
    <div className="grid-2">
      <div className="card">
        <div className="card-header"><h2>{t.header_checklist}</h2></div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
          {items.map((item) => (
            <div key={item.key} className={`check-item ${item.ok ? "ok" : "warn"}`}>
              <span className="check-icon">{item.ok ? <CheckCircle2 size={16} style={{ color: "var(--status-ok)" }} /> : <XCircle size={16} style={{ color: "var(--status-warn)" }} />}</span>
              <div className="check-detail">
                <span className="check-label">{item.ok ? t.val_ok : t.val_wait} · {item.label}</span>
                <span className="check-desc">{item.detail}</span>
              </div>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn btn-primary" onClick={async () => {
            setLog(t.log_e2e_running);
            const d = await fetch(`${API}/product/run_e2e`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "dry-run", seconds: 20, use_mock_llm: true, chaos: "none" }) }).then((r) => r.json());
            setItems(d.checklist ?? []); setLog(d.ok ? t.log_e2e_passed.replace("{path}", d.report_path ?? "") : t.log_e2e_failed.replace("{error}", d.error ?? ""));
          }}>{t.btn_run_e2e}</button>
          <button className="btn" onClick={async () => setItems((await fetch(`${API}/product/checklist`).then((r) => r.json())).items ?? [])}>{t.btn_refresh_checklist}</button>
          <button className="btn" onClick={async () => setReport(await fetch(`${API}/product/latest_report`).then((r) => r.json()))}>{t.btn_latest_report}</button>
        </div>
      </div>
      <div className="card">
        <div className="card-header"><h2>{t.header_run_result}</h2></div>
        <pre>{report ? JSON.stringify(report, null, 2) : log}</pre>
      </div>
    </div>
  );
}

// ─── Shared components ───

function HealthItem({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="status-card">
      <span className="status-card-label">{label}</span>
      <span className={`status-card-value ${ok ? "ok" : "warn"}`}>{value}</span>
    </div>
  );
}

function modeLabel(t: typeof import("./i18n/zh").default, mode: AgentState["mode"]): string {
  return { STOPPED: t.mode_stopped, RUNNING: t.mode_running, PAUSED: t.mode_paused, EMERGENCY_STOPPED: t.mode_emergency }[mode];
}

function pageTitle(t: typeof import("./i18n/zh").default, page: Page): string {
  return {
    dashboard: t.nav_dashboard, monitor: t.nav_monitor, reports: t.nav_reports,
    settings: t.nav_settings, calibration: t.nav_calibration, skills: t.nav_skills,
    planner: t.nav_planner, companion: t.nav_companion, combat: t.nav_combat,
    checklist: t.nav_checklist,
  }[page];
}

function demoSkillPayload() {
  return {
    skill_id: "gui_demo_skill", name: "GUI Demo Skill", type: "ui", version: 1,
    metadata: { source: "gui" }, environment_profile: "default_1920x1080",
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

// ─── Mount ───

createRoot(document.getElementById("root")!).render(<App />);
