// Differential front end: entry module. Wires the header, the start screen and
// the session panels to the FastAPI backend. No framework, no build step, no
// external requests.

import { api, ApiError } from "./modules/api.js";
import {
  h, icon, hydrateIcons, setIcon, announce, toast, busyButton, replaceChildren,
} from "./modules/dom.js";
import { initTheme, currentTheme } from "./modules/theme.js";
import { SchematicView } from "./modules/schematic.js";
import { BeliefPanel } from "./modules/belief.js";
import { NextCard, ReadingsTable, SafetyBanner } from "./modules/panels.js";
import { ChatPanel, EXAMPLE_COMPLAINT } from "./modules/chat.js";
import { TicketDialog } from "./modules/ticket.js";
import { fmtElapsed, pct } from "./modules/format.js";

const SESSION_KEY = "differential.session";
const params = new URLSearchParams(window.location.search);

const app = {
  health: null,
  circuits: [],
  circuitCache: new Map(),
  selected: null,
  state: null,
  circuit: null,
  busy: false,
  replay: null, // {name, frames, i, ticket} while a recorded session is being played back
};

const $ = (id) => document.getElementById(id);
const els = {
  select: $("circuit-select"),
  modeBadge: $("mode-badge"),
  newUnit: $("new-unit-btn"),
  ticketBtn: $("ticket-btn"),
  revealBtn: $("reveal-btn"),
  themeBtn: $("theme-btn"),
  start: $("start-view"),
  session: $("session-view"),
  side: $("side"),
  overlay: $("loading-overlay"),
  overlayTitle: $("loading-title"),
  overlaySub: $("loading-sub"),
};

// ------------------------------------------------------------ storage (guarded)
function storeSession(sid) {
  try {
    if (sid) window.sessionStorage.setItem(SESSION_KEY, sid);
    else window.sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* storage unavailable: the session just is not restored after a reload */
  }
}

function storedSession() {
  try {
    return window.sessionStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

// ------------------------------------------------------------------- helpers
const canAct = () => Boolean(app.state) && !app.busy && !app.replay;

async function getCircuit(cid) {
  if (app.circuitCache.has(cid)) return app.circuitCache.get(cid);
  const c = await api.circuit(cid);
  app.circuitCache.set(cid, c);
  return c;
}

function circuitSummary(cid) {
  return app.circuits.find((c) => c.id === cid) || null;
}

function shortName(name) {
  return String(name || "").replace(/^Block \d+ - /, "");
}

function setMode(mode) {
  const m = mode || (app.health && app.health.default_mode) || "offline";
  const label = { offline: "Offline", live: "Live", replay: "Replay" }[m] || m;
  const help = {
    offline: "Offline: deterministic templates built from tool results; no model calls.",
    live: `Live: Claude (${(app.health && app.health.model) || "model"}) chooses tools and writes the explanations.`,
    replay: app.replay
      ? "Replay: a recorded session played back with no engine or network call. Right arrow or space: next step; left arrow: back; Escape: leave."
      : "Replay: the live code path served from recorded responses; no API key needed.",
  }[m] || "";
  els.modeBadge.dataset.mode = m;
  els.modeBadge.querySelector(".mode-text").textContent = label;
  els.modeBadge.title = help;
  els.modeBadge.setAttribute("aria-label", `Agent mode: ${label}. ${help}`);
}

function sessionLost(err) {
  return err instanceof ApiError && err.status === 404 && /unknown session/i.test(err.message);
}

function handleError(err, context) {
  if (sessionLost(err)) {
    toast("This session no longer exists on the server (it may have restarted). Start a new unit.");
    endSession();
    return err.message;
  }
  const msg = err instanceof ApiError ? err.message : String(err && err.message ? err.message : err);
  toast(context ? `${context}: ${msg}` : msg);
  return msg;
}

/** Run one server action; returns "" on success or an error message. */
async function act(fn, { button = null, typing = null } = {}) {
  if (app.busy) return "Please wait for the current step to finish.";
  app.busy = true;
  document.body.classList.add("is-busy");
  refreshHeader();
  const restore = busyButton(button);
  if (typing) chat.setBusy(true, typing);
  let res = null;
  let error = "";
  try {
    res = await fn();
  } catch (err) {
    error = handleError(err);
  }
  // Leave the busy state before re-rendering so the new controls come out enabled.
  app.busy = false;
  document.body.classList.remove("is-busy");
  restore();
  if (typing) chat.setBusy(false);
  if (res && app.state) {
    if (res.state) setState(res.state);
    else if (res.session_id) setState(res);
    if (res.reply) error = replyError(res.reply);
  }
  refreshHeader();
  return error;
}

/** The agent reports rejected readings as a normal reply ("I couldn't record that: ..."). */
function replyError(reply) {
  const text = String((reply && reply.text) || "");
  return /^I couldn['’]t record that/i.test(text) ? text : "";
}

// ------------------------------------------------------------------- panels
const schematic = new SchematicView($("schematic"), {
  canAct,
  measure: (key, btn) => act(() => api.measure(app.state.session_id, key), { button: btn }),
  enterReading: (key, value, btn) => act(() => api.reading(app.state.session_id, key, value), { button: btn }),
});

const banner = new SafetyBanner($("banner-slot"), {
  discharge: async (readings, btn) => {
    const err = await act(() => api.discharge(app.state.session_id, readings), { button: btn });
    if (err) return err;
    if (app.state && !app.state.discharge_verified) {
      const last = [...(app.state.transcript || [])].reverse().find((t) => t.role === "assistant");
      return last ? last.text.split("\n")[0] : "The discharge was not confirmed.";
    }
    return "";
  },
  approve: async (note, btn) => act(() => api.approveRemoval(app.state.session_id, note), { button: btn }),
  supervisor: async (name, btn) => act(() => api.supervisor(app.state.session_id, name), { button: btn }),
  bringUp: async (method, btn) => act(() => api.bringUp(app.state.session_id, method), { button: btn }),
});

const nextCard = new NextCard($("next-card"), {
  canAct,
  measure: (key, btn) => act(() => api.measure(app.state.session_id, key), { button: btn }),
  enterReading: (key, value, btn) => act(() => api.reading(app.state.session_id, key, value), { button: btn }),
  openTicket: () => openTicket(),
  focusChat: () => chat.focusInput(),
  guess: (key, btn) => act(() => api.guess(app.state.session_id, key), { button: btn }),
  focusDischarge: () => {
    const input = document.querySelector(
      ".banner .discharge-form input, .banner .approval-form input, .banner .supervisor-form input, .banner .bringup-form select");
    if (input) {
      input.scrollIntoView({ block: "center", behavior: "smooth" });
      input.focus({ preventScroll: true });
    }
  },
});

const belief = new BeliefPanel($("belief"));
const readings = new ReadingsTable($("readings"));

const chat = new ChatPanel($("chat"), {
  canAct,
  send: (text) => act(() => api.message(app.state.session_id, text), { typing: "Differential is working…" }),
  uploadPhoto: async (file) => {
    if (!app.state) return null;
    return api.photo(app.state.session_id, file);
  },
  confirmPhoto: (pid, key, value, btn) =>
    act(() => api.confirmPhoto(app.state.session_id, pid, key, value), { button: btn }),
});

const ticket = new TicketDialog($("ticket-dialog"), {
  load: () => (app.replay ? Promise.resolve(app.replay.ticket) : api.ticket(app.state.session_id)),
  signoff: async (name) => {
    const t = await api.signoff(app.state.session_id, name);
    announce(`Ticket signed off by ${name}.`);
    return t;
  },
  sessionId: () => (app.state ? app.state.session_id : ""),
});

function openTicket() {
  if (!app.state) return;
  ticket.open(els.ticketBtn);
}

// --------------------------------------------------------------- start view
function renderStart(error = "") {
  const cid = app.selected;
  const c = circuitSummary(cid);
  const startBtn = h("button", { type: "button", class: "btn btn-primary btn-lg start-btn" },
    icon("probe"), h("span", {}, "Start with a simulated unit"));
  startBtn.addEventListener("click", () => startSession(startBtn));
  const traineeBox = h("input", { type: "checkbox", id: "trainee-box", checked: Boolean(app.trainee) });
  traineeBox.addEventListener("change", () => { app.trainee = traineeBox.checked; });
  const traineeRow = h("div", { class: "trainee-row" }, traineeBox,
    h("label", { for: "trainee-box" }, "Trainee mode: commit your own next step before the tool shows its choice; high-voltage units need a named supervisor"));
  const facts = c ? [
    h("span", { class: "fact" }, h("b", { class: "num" }, String(c.components)), " parts"),
    h("span", { class: "fact" }, h("b", { class: "num" }, String(c.test_points)), " test points"),
    h("span", { class: `fact${c.high_voltage_test_points ? " fact-hv" : ""}` },
      c.high_voltage_test_points ? icon("bolt") : null,
      h("b", { class: "num" }, String(c.high_voltage_test_points)), " high-voltage"),
  ] : [];
  replaceChildren(els.start,
    h("section", { class: "panel start-card", "aria-labelledby": "start-title" },
      h("p", { class: "kicker" }, "Simulated bench demo"),
      h("h1", { id: "start-title", class: "start-title" }, "Find the failed part, one measurement at a time"),
      h("p", { class: "lede" },
        "Differential helps a qualified bench technician find the failed part in analog audio equipment. It simulates the circuit under every plausible single-part fault with realistic part tolerances, keeps a probability for every suspect and recommends the measurement expected to narrow the suspects most per unit of effort."),
      h("ol", { class: "how-list" },
        h("li", {}, h("b", {}, "Start a unit. "), "A hidden fault is drawn and the unit is simulated with ngspice."),
        h("li", {}, h("b", {}, "Describe the complaint "), `in the chat, for example “${EXAMPLE_COMPLAINT}”.`),
        h("li", {}, h("b", {}, "Measure "), "where Differential recommends and watch the belief update."),
        h("li", {}, h("b", {}, "Close with the ticket "), "and sign it off. Safety rules run in code, not in a prompt.")),
      h("div", { class: "start-circuit" },
        h("p", { class: "mini-title" }, "Circuit"),
        h("p", { class: "start-circuit-name" }, c ? c.name : cid || "–"),
        h("p", { class: "facts" }, facts)),
      traineeRow,
      startBtn,
      error ? h("div", { class: "start-error", role: "alert" }, icon("alert"), h("div", {}, error)) : null,
      h("p", { class: "fine" }, icon("info"),
        h("span", {}, "Every “Measure” reads the simulated bench. Readings can also be typed, or read from a meter photo and confirmed."))));
}

function showStart(error = "") {
  els.session.hidden = true;
  els.start.hidden = false;
  renderStart(error);
  refreshHeader();
  previewCircuit(app.selected);
}

async function previewCircuit(cid) {
  if (!cid) return;
  try {
    const c = await getCircuit(cid);
    if (app.state || app.selected !== cid) return;
    schematic.setCircuit(c);
    schematic.update({ sessionActive: false });
  } catch (err) {
    handleError(err, "Could not load the circuit");
  }
}

function endSession() {
  app.state = null;
  app.circuit = null;
  storeSession(null);
  setMode(null);
  showStart();
}

let overlayTimer = null;
function showOverlay(title, sub) {
  els.overlayTitle.textContent = title;
  els.overlaySub.textContent = sub;
  els.overlay.hidden = false;
  const t0 = performance.now();
  clearInterval(overlayTimer);
  overlayTimer = setInterval(() => {
    els.overlaySub.textContent = `${sub} (${fmtElapsed(performance.now() - t0)})`;
  }, 1000);
}

function hideOverlay() {
  clearInterval(overlayTimer);
  els.overlay.hidden = true;
}

async function startSession(button) {
  if (app.busy) return;
  const cid = app.selected;
  const c = circuitSummary(cid);
  const body = { circuit_id: cid, trainee: Boolean(app.trainee) };
  // Scripted demos (tools/screenshots.py) may fix the hidden fault and the unit seed.
  if (params.get("fault")) body.fault = params.get("fault");
  if (params.get("seed") && Number.isFinite(Number(params.get("seed")))) body.seed = Number(params.get("seed"));
  if (params.get("mode")) body.mode = params.get("mode");
  if (params.get("trainee") === "1") body.trainee = true;
  app.busy = true;
  const restore = busyButton(button);
  els.newUnit.disabled = true;
  showOverlay(`Preparing a simulated ${c ? shortName(c.name) : "unit"}…`,
    "A hidden fault is drawn and the unit is simulated with ngspice");
  try {
    const st = await api.newSession(body);
    app.circuit = await getCircuit(st.circuit);
    app.busy = false;
    setState(st);
    announce(`New unit ready on the ${app.circuit.name}. Describe the complaint to begin.`);
    chat.focusInput();
  } catch (err) {
    app.busy = false;
    const name = c ? `“${c.name}”` : cid;
    let msg;
    if (err instanceof ApiError && err.status >= 500) {
      msg = `Could not start a unit on ${name}. The server could not prepare this circuit (HTTP ${err.status}); its engine model may not be trained yet. Choose another circuit, or try again later.`;
    } else if (err instanceof ApiError && err.status === 400) {
      msg = `Could not start a unit: ${err.message}`;
    } else {
      msg = `Could not start a unit on ${name}: ${err.message || err}`;
    }
    if (app.state) toast(msg);
    else showStart(msg);
  } finally {
    restore();
    hideOverlay();
    refreshHeader();
  }
}

// ---------------------------------------------------------------- rendering
function setState(st) {
  const prev = app.state;
  app.state = st;
  if (!app.replay) storeSession(st.session_id);
  if (!app.circuit || app.circuit.id !== st.circuit) {
    app.circuit = app.circuitCache.get(st.circuit) || app.circuit;
  }
  const circuit = app.circuit;
  els.start.hidden = true;
  els.session.hidden = false;
  setMode(st.mode);
  schematic.setCircuit(circuit);
  schematic.update({ readings: st.readings || [], pending: st.pending, sessionActive: true });
  const bannerChanged = banner.update(st);
  nextCard.update(st, circuit);
  belief.update(st, circuit);
  chat.update(st, circuit);
  readings.update(st, circuit);
  refreshHeader();

  const said = [];
  // A new recommendation (or a new safety banner) is the next thing to read: bring
  // the top of the column into view, e.g. after the complaint was sent from the chat.
  const samePrev = prev && prev.session_id === st.session_id;
  const pendingKey = (p) => (p ? `${p.key}|${p.blocked || ""}` : "");
  const newStep = samePrev && pendingKey(prev.pending) !== pendingKey(st.pending);
  if ((newStep || bannerChanged) && els.side.scrollTop > 0) {
    els.side.scrollTo({ top: 0, behavior: "auto" });
  }
  const before = samePrev ? (prev.readings || []).length : 0;
  const now = (st.readings || []).length;
  if (now > before) {
    const r = st.readings[now - 1];
    const top = (st.top_hypotheses || []).find((x) => x.fault !== "unmodeled");
    said.push(`Recorded ${r.key} = ${r.text}.${top ? ` Leading suspect: ${top.label}, ${pct(top.p)}.` : ""}`);
  }
  if (bannerChanged && st.banner) said.push(`Safety: ${st.banner.title}`);
  if (newStep && st.pending && !st.pending.blocked) {
    said.push(`Next: ${st.pending.what} at ${st.pending.test_point || st.pending.part || st.pending.key}.`);
  }
  if (said.length) announce(said.join(" "));
}

let revealArmed = false;
let revealTimer = null;
let newArmed = false;
let newTimer = null;

function refreshHeader() {
  const has = Boolean(app.state);
  els.ticketBtn.disabled = !has || app.busy;
  const revealed = Boolean(app.state && app.state.revealed);
  els.revealBtn.disabled = !has || app.busy || revealed;
  els.revealBtn.querySelector(".btn-text").textContent = revealed ? "Fault revealed"
    : revealArmed ? "Click again to end and reveal" : "Reveal hidden fault";
  els.newUnit.disabled = app.busy || !app.circuits.length;
  els.newUnit.querySelector(".btn-text").textContent = newArmed ? "Click again: new unit" : "New unit";
  const differs = has && app.selected && app.state.circuit !== app.selected;
  els.newUnit.classList.toggle("is-highlighted", Boolean(differs));
  const sel = circuitSummary(app.selected);
  els.newUnit.title = differs && sel ? `Start a new unit on the ${sel.name}` : "Start a new simulated unit";
  els.select.disabled = !app.circuits.length || app.busy;
}

// ------------------------------------------------------------------- header
function bindHeader(theme) {
  els.themeBtn.addEventListener("click", () => theme.toggle());
  els.select.addEventListener("change", () => {
    app.selected = els.select.value;
    if (!app.state) showStart();
    refreshHeader();
  });
  els.newUnit.addEventListener("click", () => {
    const inProgress = app.state && (app.state.readings || []).length > 0
      && !(app.state.belief && app.state.belief.would_stop);
    if (inProgress && !newArmed) {
      newArmed = true;
      refreshHeader();
      clearTimeout(newTimer);
      newTimer = setTimeout(() => { newArmed = false; refreshHeader(); }, 4000);
      return;
    }
    newArmed = false;
    clearTimeout(newTimer);
    startSession(els.newUnit);
  });
  els.ticketBtn.addEventListener("click", () => openTicket());
  els.revealBtn.addEventListener("click", async () => {
    if (!app.state) return;
    const done = app.state.belief && app.state.belief.would_stop;
    if (!done && !revealArmed) {
      revealArmed = true;
      refreshHeader();
      clearTimeout(revealTimer);
      revealTimer = setTimeout(() => { revealArmed = false; refreshHeader(); }, 4000);
      return;
    }
    revealArmed = false;
    clearTimeout(revealTimer);
    const err = await act(() => api.reveal(app.state.session_id, !done), { button: els.revealBtn });
    if (!err && app.state && app.state.revealed) {
      announce(`Hidden fault: ${app.state.revealed.label}.`);
      document.querySelector(".reveal-callout")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  });
}

function onTheme(t) {
  const dark = t === "dark";
  setIcon(els.themeBtn.querySelector(".icon"), dark ? "sun" : "moon");
  els.themeBtn.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
  els.themeBtn.title = dark ? "Switch to light theme" : "Switch to dark theme";
  schematic.setTheme(t);
}

function populateCircuits() {
  replaceChildren(els.select, app.circuits.map((c) => h("option", { value: c.id },
    `${shortName(c.name)}${c.high_voltage_test_points ? " (HV)" : ""}`)));
  els.select.value = app.selected;
  els.select.title = "Circuit for the next unit";
}

// --------------------------------------------------------------------- init
async function init() {
  hydrateIcons();
  const theme = initTheme(onTheme);
  onTheme(currentTheme());
  bindHeader(theme);

  const [health, circuits] = await Promise.allSettled([api.health(), api.circuits()]);
  if (health.status === "fulfilled") app.health = health.value;
  setMode(null);
  if (circuits.status === "fulfilled") {
    app.circuits = circuits.value.circuits || [];
  } else {
    replaceChildren(els.select, h("option", {}, "Unavailable"));
    showStart(`The server did not return the circuit list: ${circuits.reason.message}. Check that the Differential server is running, then reload.`);
    return;
  }
  const wanted = params.get("circuit");
  app.selected = app.circuits.some((c) => c.id === wanted) ? wanted
    : (app.circuits.find((c) => c.id === "channel_strip") || app.circuits[0] || {}).id;
  populateCircuits();

  const sid = storedSession();
  if (sid) {
    try {
      const st = await api.state(sid);
      app.circuit = await getCircuit(st.circuit);
      app.selected = st.circuit;
      els.select.value = st.circuit;
      setState(st);
      return;
    } catch {
      storeSession(null);
    }
  }
  showStart();
}

// ------------------------------------------------------------------ replay
// Demo fallback (M5 runbook): Shift+R plays a recorded session frame by frame, with
// no engine, simulator or network call (recorded by tools/record_replay.py).
async function startReplay(name = "demo") {
  if (app.busy) return;
  let data;
  try {
    data = await api.replay(name);
  } catch (err) {
    toast(`No recorded session "${name}" (run tools/record_replay.py): ${err.message || err}`);
    return;
  }
  const frames = [...(data.frames || [])];
  if (data.reveal) frames.push({ caption: "The hidden fault is revealed.", state: data.reveal });
  if (!frames.length) return;
  app.circuit = await getCircuit(data.circuit);
  app.replay = { name, frames, i: 0, ticket: data.ticket };
  showReplayFrame();
}

function showReplayFrame() {
  const r = app.replay;
  const f = r.frames[r.i];
  setState({ ...f.state, mode: "replay" });
  setMode("replay");
  announce(`Replay ${r.i + 1} of ${r.frames.length}: ${f.caption}`);
  let bar = document.getElementById("replay-caption");
  if (!bar) {
    bar = h("div", { id: "replay-caption", class: "replay-caption", role: "status" });
    document.body.append(bar);
  }
  bar.hidden = false;
  bar.textContent = `Replay ${r.i + 1}/${r.frames.length} · ${f.caption}  (→ next · ← back · Esc leave)`;
}

function stepReplay(delta) {
  const r = app.replay;
  const i = Math.min(r.frames.length - 1, Math.max(0, r.i + delta));
  if (i === r.i) return;
  r.i = i;
  showReplayFrame();
}

function leaveReplay() {
  const bar = document.getElementById("replay-caption");
  if (bar) bar.hidden = true;
  app.replay = null;
  app.state = null;
  showStart();
  setMode(null);
  refreshHeader();
}

document.addEventListener("keydown", (e) => {
  const typing = e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
  if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.shiftKey && (e.key === "R" || e.key === "r")) {
    e.preventDefault();
    if (!app.replay) startReplay(params.get("replay") || "demo");
    return;
  }
  if (!app.replay) return;
  if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); stepReplay(1); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); stepReplay(-1); }
  else if (e.key === "Escape") { e.preventDefault(); leaveReplay(); }
});

init().then(() => {
  if (params.get("replay")) startReplay(params.get("replay"));
}).catch((err) => {
  toast(`The app failed to start: ${err.message || err}`);
});

// Expose a tiny read-only hook for the screenshot/verification script.
window.differential = {
  get state() { return app.state; },
  get busy() { return app.busy; },
};
