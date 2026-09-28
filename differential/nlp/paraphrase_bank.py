"""Held-out paraphrase bank for the channel-strip diagnosis benchmark.

This module is the held-out paraphrase set. A benchmark case is a set of
observed symptom facts; the renderer turns each case into a brief free-text
complaint by drawing one phrase per fact from this bank, in the voice of one
of three personas:

    bench_tech     terse job note from a professional repair technician,
                   using bench jargon (level, response, tone in, scope, meter)
    hobbyist       informal, somewhat wordy and sometimes imprecise forum post
    studio_client  studio owner or engineer-client with no electronics
                   knowledge, describing how the unit sounds

The wording was written independently of the keyword extractor, without
looking at its vocabulary or its rules, so that the benchmark measures how
well symptom extraction generalises to phrasing it has never seen. It is never
used for tuning: do not mine it for keywords, do not copy its wording into the
extractor, and do not reword it in response to benchmark failures. Any of
these would contaminate the held-out set and inflate the scores it reports.

Structure
---------
``PARAPHRASE_BANK[persona][key]`` is a list of phrase variants. The keys are
the same for every persona and are listed in the comment above the dict.

``SEVERITY_TAG_P[persona][severity]`` is a brief sentence, leading space
included, appended after the last symptom sentence of a case. The "mild" and
"severe" entries are generic enough to follow any symptom; "moderate" is the
empty string.

Placeholders
------------
Some ``low_gain`` variants contain ``{db}``, roughly how many dB down the
level is; the others carry no number. Every variant of the internal
operating-voltage symptom contains ``{stage}``, a lower-case noun phrase such
as "the power supply" or "the gain stage", so it never starts a sentence.
These are the only braces in any phrase, so ``str.format(db=..., stage=...)``
is safe on every string in the bank.

Every phrase is plain ASCII and one or two sentences long, names no parts and
no fault mechanisms, and each symptom phrase describes only its own symptom;
the introductory and closing sentences carry no symptom content. The wording
deliberately mixes British and American usage.
"""

from __future__ import annotations

# Keys, identical for every persona (4 to 6 variants each):
#   opener        introductory sentence about the unit, no symptom content
#   no_output     the unit passes no audio at all
#   low_gain      output level lower than it should be; some variants use {db}
#   hum           low-frequency mains hum or buzz at the output
#   distortion    output distorted or clipped at normal level
#   dc_at_output  DC present at the output (thumps when patching, meter reading)
#   bias_drift    DC operating voltages inside one part of the unit measure
#                 wrong; every variant uses {stage}
#   bass_loss     low-frequency response missing (thin sound)
#   treble_loss   high-frequency response missing (dull sound)
#   closer        optional final sentence, no symptom content; includes ""
PARAPHRASE_BANK: dict[str, dict[str, list[str]]] = {
    "bench_tech": {
        "opener": [
            "Job sheet: mono channel strip booked in for repair.",
            "Service ticket: single-channel preamp strip, customer unit.",
            "Bench note: customer's mono channel strip, checked with tone and scope.",
            "Channel strip in for service, single channel, rack mount.",
            "Unit received: mono preamp channel strip, first look today.",
        ],
        "no_output": [
            "No output with tone in.",
            "Tone in, nothing out.",
            "Passes nothing with tone applied.",
            "Completely mute at the line out with 1 kHz applied.",
            "Test tone not reaching the output, checked on scope and meter.",
            "Signal path dead from input to output.",
        ],
        "low_gain": [
            "Output level down about {db} dB.",
            "Gain low, roughly {db} dB under spec.",
            "Measures {db} dB or so shy of nominal at the output.",
            "Gain under spec with tone in.",
            "Level reads low on the meter against the reference unit.",
            "Insufficient gain through the unit, output under nominal.",
        ],
        "hum": [
            "Mains hum on the output.",
            "50 Hz hum at the output, visible on the scope.",
            "60 cycle buzz riding on the output.",
            "Constant low-frequency drone at the output, mains related.",
            "Line-frequency content on the output with the input terminated.",
            "Steady hum and buzz audible at the output.",
        ],
        "distortion": [
            "Distorted at nominal level.",
            "Clipping on the scope at normal operating level.",
            "Sine in, flat-topped waveform out at +4 dBu.",
            "THD elevated at standard operating level.",
            "Audible breakup on tone at normal level.",
            "Waveform squared off on the scope at nominal drive.",
        ],
        "dc_at_output": [
            "DC present at the output.",
            "Meter reads standing DC on the output at idle.",
            "Output not centred on zero volts at idle.",
            "Thumps on patching the output, DC measured there.",
            "Voltage offset on the line out, confirmed with the meter.",
            "Thump heard on connecting and disconnecting the output.",
        ],
        "bias_drift": [
            "DC conditions in {stage} measure wrong.",
            "Operating voltages in {stage} out of tolerance.",
            "Bias across {stage} off against the service data.",
            "Quiescent readings in {stage} not where they should be.",
            "Static voltages around {stage} don't agree with the schematic.",
            "Meter shows incorrect DC figures throughout {stage}.",
        ],
        "bass_loss": [
            "LF response rolled off.",
            "Bass response missing, sounds thin.",
            "Sweep shows the low end collapsing early.",
            "Response falls away below a couple of hundred Hz.",
            "No bottom end on program material.",
            "Low frequencies down relative to midband.",
        ],
        "treble_loss": [
            "HF response rolled off.",
            "Treble missing, dull on programme material.",
            "Top end gone on the sweep.",
            "Response dies away above a few kHz.",
            "Highs attenuated, output sounds dull.",
            "Upper octaves rolling away early on the sweep.",
        ],
        "closer": [
            "",
            "Please advise.",
            "Customer awaiting quote.",
            "Logged for further diagnosis.",
            "Needs turning round this week.",
        ],
    },
    "hobbyist": {
        "opener": [
            (
                "Hey all, hoping someone can help me out "
                "with a channel strip I picked up second hand."
            ),
            (
                "Hi folks, first post here, I've got a "
                "single-channel preamp strip that has me stumped."
            ),
            (
                "So I finally built the mono channel strip "
                "kit I've been meaning to do for ages."
            ),
            (
                "Evening all, I've been messing about with "
                "an old channel strip I rescued from a skip."
            ),
            (
                "Hey y'all, I got a used mono channel strip "
                "off a buddy and could use some advice."
            ),
        ],
        "no_output": [
            (
                "I've tried a mic, a synth and a guitar "
                "and it won't pass any audio at all."
            ),
            "I plug a guitar in and get nothing out of it, not a whisper.",
            "Doesn't matter what I feed it, it passes absolutely nothing.",
            "Signal goes in and just vanishes, zero output.",
            "No sound whatsoever makes it through to the other end.",
            "It's gone totally dead as far as audio goes.",
        ],
        "low_gain": [
            "The output is quieter than it should be, I reckon about {db} dB down.",
            (
                "Level seems to be down {db} dB or so "
                "compared to the specs, if my maths is right."
            ),
            "I have to crank it right up just to get a normal volume out of it.",
            "Everything comes out weak compared to my other pres.",
            "It's about {db} dB quieter than my other preamp, give or take.",
            (
                "The gain seems down on what it should "
                "be, it just doesn't get loud enough."
            ),
        ],
        "hum": [
            (
                "There's this hum on the output the whole "
                "time, even with nothing plugged into the input."
            ),
            "It's got an annoying mains buzz sitting in the background.",
            "I'm getting a constant low growl through the monitors.",
            "There's a drone under everything, 50 or 60 cycle I think, not sure which.",
            "A steady humming comes through the speakers whether I'm playing or not.",
            "You can hear mains noise creeping in during the pauses.",
        ],
        "distortion": [
            "At normal levels it sounds fuzzy and crunchy, like it's clipping.",
            (
                "Anything I run through it comes out sounding "
                "distorted, even with everything set to sensible levels."
            ),
            "It's breaking up even though I'm nowhere near pushing it.",
            "Vocals sound gritty and mangled at perfectly ordinary levels.",
            "It sounds like an overdriven guitar amp, even with the gain set sensibly.",
            (
                "Clean signals come out with a nasty "
                "rasp on them, and I'm not running it hot."
            ),
        ],
        "dc_at_output": [
            (
                "Every time I plug or unplug the output "
                "there's a thump through the speakers."
            ),
            (
                "My cheap multimeter shows a few volts of DC "
                "sitting on the output, which surely can't be right."
            ),
            (
                "I think there's DC on the output? The "
                "meter shows a couple of volts there at idle."
            ),
            (
                "Patching it in or out makes a nasty pop, and "
                "the speaker cones look like they sit pushed out."
            ),
            (
                "With nothing playing I still measure a fixed "
                "voltage across the output, which seems wrong."
            ),
            "According to my meter there's a DC offset on the output.",
        ],
        "bias_drift": [
            (
                "I stuck my multimeter on {stage} and the "
                "voltages are nowhere near what the schematic says."
            ),
            "Checked the DC readings around {stage} and they're all over the place.",
            "Went round {stage} with the meter and loads of the readings are wrong.",
            "The bias in {stage} looks totally out of whack to me.",
            (
                "The operating voltages inside {stage} don't "
                "line up with the service manual at all."
            ),
            (
                "Probing about in {stage}, the voltages I'm "
                "reading seem wonky compared to the build notes."
            ),
        ],
        "bass_loss": [
            "It sounds thin, like the low end has been sucked out.",
            (
                "Kick drums and bass guitar have no weight at "
                "all when I run them through it, which is odd."
            ),
            "There's basically no bass coming through anymore.",
            "Everything sounds tinny, the bottom end just isn't there.",
            "The lows have gone AWOL and it all sounds a bit anaemic.",
            "Bass response has pretty much disappeared, everything feels lightweight.",
        ],
        "treble_loss": [
            (
                "Everything sounds dull and muffled, "
                "like there's a blanket over the speakers."
            ),
            "The top end has gone, cymbals have no sizzle at all.",
            "Treble's just vanished and it sounds murky.",
            "It's like someone stuck a sock over the mic, all the highs are missing.",
            "Hi-hats and vocals have lost all their air and shimmer.",
            "It's lost the high frequencies and everything sounds woolly.",
        ],
        "closer": [
            "",
            "Any ideas would be massively appreciated!",
            "Cheers in advance.",
            "Happy to post pics if it helps, thanks!",
            "What would you check first?",
        ],
    },
    "studio_client": {
        "opener": [
            (
                "Hi, I run a small recording studio and "
                "one of our channel strips needs looking at."
            ),
            "We've got a channel strip in the control room that's been playing up.",
            (
                "I'm bringing in the channel strip from "
                "our vocal chain for you to look at."
            ),
            "This is the preamp strip we use on most of our tracking sessions.",
            "Our studio's go-to channel strip needs some attention.",
        ],
        "no_output": [
            "Nothing comes through it at all anymore.",
            "It's gone completely mute, we can't get any sound out of it.",
            "We plug a mic in and there's not a peep.",
            "Whatever we send into it, nothing comes out the other side.",
            "It's stopped passing audio entirely.",
            "The meters on the desk don't move at all when we route through it.",
        ],
        "low_gain": [
            (
                "It's quieter than it used to be, we "
                "have to push everything up to compensate."
            ),
            (
                "The level coming out is lower than our other "
                "channels, maybe {db} dB going by the meters."
            ),
            (
                "Compared to our other strip it's about {db} dB down, "
                "so the desk channel is nearly maxed out to match."
            ),
            "Vocals come through weak and we're running out of gain.",
            "It just doesn't get as loud as it should anymore.",
            "Our engineer thinks it's roughly {db} dB down on where it should be.",
        ],
        "hum": [
            "There's a hum behind everything that never goes away.",
            "We're hearing a low drone in the background on every take.",
            "It's got a buzz you can hear in the gaps between songs.",
            (
                "It's like there's a fridge running in "
                "the next room the whole time we record."
            ),
            "You can hear an electrical humming under all our recordings.",
            "Every track we cut through it has a 60 cycle hum on it.",
        ],
        "distortion": [
            "Everything comes out splattery and harsh at our usual recording levels.",
            "Vocals come out distorted even at a normal singing level.",
            (
                "It sounds torn up and ragged, as if it's "
                "being overdriven, but we aren't pushing it."
            ),
            "There's a nasty jagged edge on everything at perfectly normal levels.",
            (
                "Clean sources come out dirty, like they've "
                "been run through a cheap effects pedal."
            ),
            (
                "It breaks up at the levels we always "
                "track at, and that never used to happen."
            ),
        ],
        "dc_at_output": [
            "There's a thump every time we patch it in or out.",
            "When we plug the output in, the speakers jump with a clunk.",
            "Our tech put a meter on it and said there's DC on the output.",
            "Repatching it at the bay always makes an alarming bang.",
            (
                "Our maintenance engineer measured a steady "
                "voltage on the output even with nothing playing."
            ),
            (
                "Apparently there's DC coming out of it, and "
                "patching it makes a thud in the monitors."
            ),
        ],
        "bias_drift": [
            "Our tech had a look inside and said the voltages in {stage} are off.",
            "The repair guy measured {stage} and told us the DC readings were wrong.",
            (
                "A friend who knows electronics checked "
                "{stage} and said the numbers didn't look right."
            ),
            "We were told the internal voltages around {stage} are out of spec.",
            (
                "According to our maintenance guy, the "
                "bias in {stage} isn't where it should be."
            ),
            (
                "Someone who knows about this stuff metered "
                "{stage} and said the readings were all wrong."
            ),
        ],
        "bass_loss": [
            "It sounds thin, there's no weight in the low end anymore.",
            "The bass has disappeared and kick drums have no body at all.",
            "Everything sounds small and weedy, the bottom end has vanished.",
            "Bass guitar and kick drum just don't have any oomph anymore.",
            "It's lost all its warmth and fullness down at the bottom.",
            "The low end is gone, everything sounds skinny.",
        ],
        "treble_loss": [
            "It sounds dull, like it's behind a curtain.",
            "The top end is gone, cymbals sound like they're under a duvet.",
            "Vocals have lost their air and everything is muffled.",
            "It sounds dark now, the sparkle on acoustic guitars has disappeared.",
            "The highs sound smothered and everything has lost its crispness.",
            "There's no treble anymore, it's lost all its brightness.",
        ],
        "closer": [
            "",
            "Could you let me know what it'll cost to fix?",
            "We need it back for a session next week.",
            "Thanks for taking a look.",
            "Let me know if you need anything else from us.",
        ],
    },
}

# Appended after the last symptom sentence of a case (leading space included).
# "moderate" adds nothing.
SEVERITY_TAG_P: dict[str, dict[str, str]] = {
    "bench_tech": {
        "mild": " Marginal but repeatable.",
        "moderate": "",
        "severe": " Gross, unmissable on first check.",
    },
    "hobbyist": {
        "mild": " It's pretty subtle, to be fair.",
        "moderate": "",
        "severe": " And it's seriously bad, not subtle at all.",
    },
    "studio_client": {
        "mild": " It's only slight, but it's there.",
        "moderate": "",
        "severe": " It's really bad, impossible to ignore.",
    },
}
