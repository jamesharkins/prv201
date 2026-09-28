"""Benchmark complaint text from physics-derived symptom facts (§2.4).

Each evaluation case's simulated observables give symptom facts
(``derive_facts``); this module renders them as a complaint in one of three
personas. Offline, text comes from template banks; in live mode it can come from
Claude with a different prompt (``generate_llm``). Two independent banks exist:
``MAIN_BANK`` (used to develop the offline extractor) and the held-out
``PARAPHRASE_BANK`` in ``paraphrase_bank.py`` (written separately, never used
for tuning). ``leakage`` rejects any text that names a component, a fault label
or a part kind.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from differential.engine.symptom_prior import SymptomFacts

PERSONAS = ("bench_tech", "hobbyist", "studio_client")
STAGE_WORDS = {
    "psu_lv": "the power supply",
    "psu_hv": "the high-voltage supply",
    "triode": "the preamp section",
    "tone": "the tone section",
    "opamp": "the gain stage",
    "driver": "the output stage",
}

MAIN_BANK: dict[str, dict[str, list[str]]] = {
    "bench_tech": {
        "opener": ["Channel strip on the bench.", "Unit in for service.", "Single-channel strip, customer unit.",
                   "Strip came in today."],
        "no_output": ["No output.", "Dead at the output, nothing passes with a tone in.",
                      "Zero signal at line out."],
        "low_gain": ["Output roughly {db} dB down.", "Gain low, about {db} dB under what it should be.",
                     "Level is down around {db} dB."],
        "hum": ["Hum on the output with no input.", "120 Hz buzz at the output.", "Hum floor is way up."],
        "distortion": ["Distorts on a 1 kHz tone at normal level.", "Clipping at nominal level.",
                       "Audible distortion, THD well above normal."],
        "dc_at_output": ["DC sitting on the output jack.", "Output shows a DC offset."],
        "bias_drift": ["DC readings in {stage} look off.", "Bias looks wrong in {stage}."],
        "bass_loss": ["Low end rolled off.", "Bass response is down."],
        "treble_loss": ["Top end rolled off.", "HF response is down."],
        "closer": ["", "Nothing else checked yet.", "Haven't gone further yet."],
    },
    "hobbyist": {
        "opener": ["I picked up this channel strip second hand and have a problem.",
                   "My vintage-style channel strip started acting up.",
                   "Hoping someone can help with my preamp strip."],
        "no_output": ["It powers up but no sound comes out at all.",
                      "The lights are on but there is no audio at the output.",
                      "It's completely silent, nothing coming out."],
        "low_gain": ["It works but it is a lot quieter than it used to be, maybe {db} dB.",
                     "The output is weak, I have to turn everything way up.",
                     "It has lost volume compared to before."],
        "hum": ["There's a hum like a fridge behind everything.",
                "I get a steady buzz even with nothing plugged in.",
                "A mains hum has appeared that wasn't there before."],
        "distortion": ["It sounds fuzzy and broken up even at normal levels.",
                       "Clean signals come out distorted.",
                       "Everything sounds gritty now."],
        "dc_at_output": ["My speaker makes a thump and the meter shows DC on the output.",
                         "I measured DC on the output, which seems wrong."],
        "bias_drift": ["I measured some voltages and the ones around {stage} look off compared to what I'd expect.",
                       "My meter readings in {stage} don't look right."],
        "bass_loss": ["It also sounds thin, the bass is gone.", "There's no low end any more."],
        "treble_loss": ["It sounds dull and muffled.", "The highs are gone, it sounds dark."],
        "closer": ["Any ideas where to start?", "Not sure what to check first.", "Thanks in advance!"],
    },
    "studio_client": {
        "opener": ["Our main vocal channel has a problem.", "One of our channel strips isn't right.",
                   "Booking a repair for a strip from our studio."],
        "no_output": ["It stopped passing audio entirely.", "We get nothing out of it now.",
                      "It's dead, no signal at all."],
        "low_gain": ["It's much quieter than our other channels.", "We have to crank it to get normal level.",
                     "The level dropped noticeably."],
        "hum": ["There's a buzz under everything we record.", "It hums, you can hear it in quiet passages.",
                "A hum showed up on the channel."],
        "distortion": ["Vocals sound harsh and broken up.", "It distorts even on quiet singers.",
                       "Everything through it sounds crunchy."],
        "dc_at_output": ["There's a loud thump when we patch it in.", "Our engineer says there's DC on the output."],
        "bias_drift": ["Our engineer measured it and says something in {stage} reads wrong."],
        "bass_loss": ["It sounds thin, no weight in the low end.", "The bottom end has disappeared."],
        "treble_loss": ["It sounds dull, like a blanket over it.", "The air and sparkle are gone."],
        "closer": ["We need it back for a session.", "Can you take a look?", ""],
    },
}

SEVERITY_TAG = {
    "bench_tech": {"mild": "", "moderate": "", "severe": " Severe."},
    "hobbyist": {"mild": " It's only slight.", "moderate": "", "severe": " It's really bad."},
    "studio_client": {"mild": " It's subtle but we can hear it.", "moderate": "", "severe": " It's unusable."},
}

LEAK_REF = re.compile(r"\b(?:R|C|Q|D|U|V|VR|TP)\d{1,3}\b")
LEAK_WORDS = re.compile(
    r"\b(?:open|short(?:ed)?|drift(?:ed)?|leak(?:y|age)?|esr|emission|heater|beta|hfe|gbw|bandwidth|"
    r"resistors?|capacitors?|caps?|electrolytics?|transistors?|zeners?|diodes?|potentiometers?|pots?|"
    r"op-?amps?|triodes?|valves?|tubes?|12ax7|2n3904|1n4148|1n4745a?)\b",
    flags=re.IGNORECASE,
)


def leakage(text: str) -> list[str]:
    """Tokens that would leak the answer (component refs, fault labels, part kinds)."""
    return [m.group(0) for m in LEAK_REF.finditer(text)] + [m.group(0) for m in LEAK_WORDS.finditer(text)]


def _stage_words(facts: SymptomFacts, tp_stage: dict[str, str]) -> str:
    for tp in facts.drift_tps:
        stage = tp_stage.get(tp)
        if stage in STAGE_WORDS:
            return STAGE_WORDS[stage]
    return "one of the stages"


def render(
    facts: SymptomFacts,
    persona: str,
    rng: np.random.Generator,
    tp_stage: dict[str, str],
    bank: dict[str, dict[str, list[str]]] | None = None,
    severity_tags: dict[str, dict[str, str]] | None = None,
) -> str:
    """Render a complaint for one persona; deterministic given ``rng``."""
    b = (bank or MAIN_BANK)[persona]
    tags = severity_tags or SEVERITY_TAG

    def pick(key: str) -> str:
        opts = b[key]
        return str(opts[int(rng.integers(len(opts)))])

    parts = [pick("opener")]
    db = None
    if facts.output_change_db is not None and facts.output_change_db < 0:
        db = max(1, round(-facts.output_change_db))
    order = ["no_output", "low_gain", "hum", "distortion", "dc_at_output", "bias_drift",
             "bass_loss", "treble_loss"]
    for feat in order:
        if not facts.features.get(feat):
            continue
        s = pick(feat)
        s = s.replace("{db}", str(db if db is not None else "a few"))
        s = s.replace("{stage}", _stage_words(facts, tp_stage))
        parts.append(s)
    if not any(facts.features.values()):
        parts.append({"bench_tech": "Customer reports it just sounds wrong.",
                      "hobbyist": "Something just sounds off but I can't describe it.",
                      "studio_client": "It just doesn't sound right any more."}[persona])
    parts[-1] = parts[-1] + tags[persona][facts.severity]
    closer = pick("closer")
    if closer:
        parts.append(closer)
    return " ".join(p for p in parts if p)


def generate_llm(facts: SymptomFacts, persona: str, client: Any, prompt_variant: str = "main") -> str:
    """Live-mode generation of a complaint from facts (cached by the client)."""
    desc = {
        "bench_tech": "a terse professional bench technician writing a job note",
        "hobbyist": "a hobbyist posting on a forum, a bit verbose, not always precise",
        "studio_client": "a studio client with no electronics knowledge describing the sound",
    }[persona]
    instructions = (
        "Write a two-to-four-sentence fault complaint about an analog audio channel strip, as "
        f"{desc}. Describe only these observed symptoms: {facts.classes()}, severity {facts.severity}. "
        "Never name components, part types, reference designators or failure mechanisms."
    )
    if prompt_variant != "main":
        instructions = (
            "Rephrase the following observations as a short customer message about their audio "
            f"gear, in the voice of {desc}: symptoms {facts.classes()}, severity {facts.severity}. "
            "Do not mention parts, part types or causes."
        )
    return str(client.text(system="You write realistic repair-request text.", user=instructions,
                           purpose=f"benchmark_{prompt_variant}"))
