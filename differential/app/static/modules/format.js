// Formatting helpers and the fixed colour/stage mappings shared by the panels.

/** Short names for measurement kinds (server keys look like "dc:TP9", "lift:R203"). */
export const KIND_SHORT = {
  dc: "DC",
  ac: "1 kHz",
  ac20: "20 Hz",
  ac20k: "20 kHz",
  hum: "Hum",
  thd: "THD",
  lift: "Lift",
};

/** Units the technician may type, first entry is the default; values are converted
 *  to the engine's base unit (volts, V/V or percent) before they are sent. */
export const KIND_UNITS = {
  dc: ["V", "mV"],
  hum: ["mV", "V"],
  ac: ["V/V", "dB"],
  ac20: ["V/V", "dB"],
  ac20k: ["V/V", "dB"],
  thd: ["%"],
};

export const BASE_UNIT = { dc: "V", hum: "V", ac: "V/V", ac20: "V/V", ac20k: "V/V", thd: "%", lift: "" };

export function kindOf(key) {
  return String(key || "").split(":")[0];
}

export function targetOf(key) {
  const parts = String(key || "").split(":");
  return parts.length > 1 ? parts.slice(1).join(":") : "";
}

/** Convert a typed value in `unit` to the base unit the engine expects. */
export function toBase(value, unit) {
  if (unit === "mV") return value / 1000;
  if (unit === "dB") return 10 ** (value / 20);
  return value;
}

/** Client-side sanity checks that mirror the server's (the server stays authoritative). */
export function validateReading(kind, base) {
  if (!Number.isFinite(base)) return "Enter a number.";
  if (["ac", "ac20", "ac20k", "hum"].includes(kind) && base < 0) return "Amplitudes and gains cannot be negative.";
  if (kind === "thd" && (base < 0 || base > 100)) return "THD must be between 0 and 100 %.";
  if (kind === "dc" && Math.abs(base) > 1000) return "That is outside the meter's range.";
  return "";
}

/** Percent for a probability in [0, 1]: "62%", "<1%", ">99%". */
export function pct(p) {
  if (p === null || p === undefined || !Number.isFinite(p)) return "–";
  if (p > 0 && p < 0.005) return "<1%";
  if (p < 1 && p > 0.995) return ">99%";
  return `${Math.round(p * 100)}%`;
}

/** "out-of-circuit component test" -> "Out-of-circuit component test" */
export function capitalize(text) {
  const t = String(text ?? "");
  return t ? t[0].toUpperCase() + t.slice(1) : t;
}

export function fmtNum(x, digits = 2) {
  if (x === null || x === undefined || !Number.isFinite(Number(x))) return "–";
  const n = Number(x);
  return Number.isInteger(n) ? String(n) : n.toFixed(digits).replace(/\.?0+$/, "");
}

export function fmtCost(c) {
  return fmtNum(c, 1);
}

/** Human label for a reading source ("simulated", "technician", "photo:ab12 (confirmed)"). */
export function sourceLabel(source) {
  const s = String(source || "");
  if (s.startsWith("photo:")) return "Photo, confirmed";
  if (s === "simulated") return "Simulated";
  if (s === "technician") return "Typed";
  if (s === "instrument") return "Instrument";
  return s || "–";
}

/** Longer description of a reading source for tooltips. */
export function sourceTitle(source) {
  const s = String(source || "");
  if (s.startsWith("photo:")) return "Read from a meter photo and confirmed by the technician";
  if (s === "simulated") return "Measured on the simulated bench";
  if (s === "technician") return "Typed in by the technician";
  return s;
}

// Fixed stage -> categorical slot mapping (colour follows the stage in every circuit).
export const STAGE_ORDER = ["psu_lv", "psu_hv", "triode", "tone", "opamp", "driver"];
export const STAGE_SHORT = {
  psu_lv: "LV supply",
  psu_hv: "HV supply",
  triode: "Triode stage",
  tone: "Tone control",
  opamp: "Op-amp stage",
  driver: "Line driver",
};

/** CSS colour (custom property) for a stage; unknown stages take slots 7-8, then grey. */
export function stageColor(stage) {
  let i = STAGE_ORDER.indexOf(stage);
  if (i < 0) {
    const extra = (stageColor.extra ||= []);
    if (!extra.includes(stage)) extra.push(stage);
    i = STAGE_ORDER.length + extra.indexOf(stage);
  }
  return i < 8 ? `var(--cat-${i + 1})` : "var(--neutral-mark)";
}

export function stageName(stage, circuit) {
  if (STAGE_SHORT[stage]) return STAGE_SHORT[stage];
  const st = circuit && circuit.stages ? circuit.stages.find((x) => x.id === stage) : null;
  return st ? st.name : stage || "Other";
}

/** Part info for a fault id like "R203:open" from the circuit payload. */
export function faultPart(fault, circuit) {
  if (!fault || fault === "healthy" || fault === "unmodeled" || !circuit) return null;
  const ref = String(fault).split(":")[0];
  return (circuit.parts || []).find((p) => p.ref === ref) || null;
}

const KIND_WORDS = {
  resistor: "resistor",
  potentiometer: "pot",
  electrolytic: "electrolytic",
  film_cap: "film cap",
  zener: "zener",
  diode: "diode",
  bjt: "transistor",
  opamp: "op-amp",
  triode: "triode",
};

const SI_PREFIX = { p: "p", n: "n", u: "µ", µ: "µ", m: "m", k: "k", Meg: "M", M: "M", G: "G" };

/** "2200u" -> "2200 µF", "1Meg" -> "1 MΩ", "2N3904" stays as is. */
export function partValue(part) {
  if (!part || !part.value) return "";
  const v = String(part.value);
  const unit = { resistor: "Ω", potentiometer: "Ω", electrolytic: "F", film_cap: "F" }[part.kind];
  if (!unit) return v;
  const m = v.match(/^([0-9]*\.?[0-9]+)\s*(Meg|[pnuµmkMG])?$/);
  if (!m) return v;
  return `${m[1]} ${m[2] ? SI_PREFIX[m[2]] : ""}${unit}`;
}

export function partDescription(part) {
  if (!part) return "";
  const kind = KIND_WORDS[part.kind] || String(part.kind || "").replace(/_/g, " ");
  return [partValue(part), kind].filter(Boolean).join(" ");
}

/** "3 s", "1 min 5 s" */
export function fmtElapsed(ms) {
  const sec = Math.max(0, Math.round(ms / 1000));
  if (sec < 60) return `${sec} s`;
  return `${Math.floor(sec / 60)} min ${sec % 60} s`;
}

export function fmtTime(t) {
  if (!t) return "";
  const d = new Date(t * 1000);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Hazard wording for the legend, popovers and aria labels. */
export const HAZARD_TEXT = {
  hv: "High voltage",
  hv_under_fault: "High voltage possible under a fault",
  lv: "Low voltage",
  unknown: "Hazard unknown (treated as high voltage)",
};

export function hazardLevel(tp) {
  const lvl = tp && tp.hazard;
  return lvl === "hv" || lvl === "hv_under_fault" || lvl === "lv" ? lvl : "unknown";
}

export function isHighVoltage(tp) {
  return hazardLevel(tp) !== "lv";
}
