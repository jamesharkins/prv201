"""Held-out paraphrase bank B (sealed): written without access to the symptom
extractor, its rules or the other banks. Never used for tuning; scored once, after
the targets are locked (target T18). Same keys, personas and placeholders as
paraphrase_bank.py."""

from __future__ import annotations

PARAPHRASE_BANK_B: dict[str, dict[str, list[str]]] = {
    "bench_tech": {
        "opener": [
            "Mono channel strip in for repair, customer drop-off.",
            "Single-channel preamp strip received from a local studio.",
            "Job ticket: one channel strip, rack unit, no manual supplied.",
            "Channel strip on the bench; serial plate intact, cosmetics good.",
            "Booked in a studio channel strip for assessment this morning.",
            "Rack channel strip arrived by courier, packaging undamaged.",
            "Hire-company channel strip checked in and tagged for service.",
            "Workshop note on a mono mic/line strip; no service history supplied.",
        ],
        "no_output": [
            "No signal at line out with tone in; the output is dead.",
            "Nothing on the scope at the output with the input driven at nominal level.",
            "Passes no audio whatsoever, though it powers up normally.",
            "Tone injected at the input, zero at the output; channel silent end to end.",
            "Dead channel: meter reads nothing on line out whatever the settings.",
            "Output flatlines; no programme gets through at any setting.",
            "Signal in, nothing out. Checked with a known-good source and lead.",
            "Complete loss of audio through the unit, input to output.",
        ],
        "low_gain": [
            "Output level about {db} dB down against spec with tone in.",
            "Gain is low: roughly {db} dB under nominal at line out.",
            "Measured output sits around {db} dB below where it should be.",
            "Level down approx {db} dB versus a reference unit on the same bench.",
            "Reads {db} dB or so low on the output meter at the usual reference setting.",
            "Gain down; needs more drive than normal to reach reference level.",
            "Output low at every gain setting, under the expected line level.",
            "Weak output; level stays under spec wherever the controls are set.",
        ],
        "hum": [
            "Mains hum on the output, present with nothing connected to the input.",
            "Scope shows a 50 Hz hum component on line out, independent of gain setting.",
            "Buzz at 120 Hz riding on the output with no signal applied.",
            "Low-frequency drone on line out; scope puts it at mains rate.",
            "Hum audible on the monitors at idle, sitting above the noise floor.",
            "Output carries 60 cycle hum, visible on the scope with the input terminated.",
            "Line-frequency buzz on the output at idle.",
            "Unwanted 100 Hz buzz on the output, constant regardless of settings.",
        ],
        "distortion": [
            "Output distorts at nominal level; sine is flat-topping on the scope.",
            "Clean test tone comes out distorted, long before rated headroom.",
            "Clipping at normal operating level, waveform squared off.",
            "THD up; audible grit on program material at normal level.",
            "Sine comes out mangled at standard level; extra harmonics on the analyser.",
            "Crunchy, harsh output at normal drive where it should be clean.",
            "Output breaks up at ordinary levels; waveform bends over on the scope.",
            "Nonlinear at nominal: tone in, distorted tone out.",
        ],
        "dc_at_output": [
            "DC present on line out; meter shows an offset at the output with no signal.",
            "Thump on patching the output into the desk, and again at switch-on.",
            "Output sits at a DC offset; test speaker cone pushed forward at rest.",
            "Pop at the output on power-up and power-down; DC measured on line out.",
            "Meter on the DC range shows standing voltage at the output; should be none.",
            "Output not DC-free; patching it in gives a thump through the monitors.",
            "DC offset on the output with the input terminated; confirmed on the DMM.",
            "DC riding at line out; thumps on the monitors when repatching.",
        ],
        "bias_drift": [
            "DC operating points in {stage} measure off nominal.",
            "Static voltages around {stage} don't match the service data.",
            "Bias conditions in {stage} are out of spec on the meter.",
            "Checked the DC throughout {stage}; readings not where they should be.",
            "Quiescent voltages on {stage} read wrong against the schematic.",
            "Metered the idle voltages inside {stage}; they don't agree with factory values.",
            "Voltage checks on {stage} fall outside tolerance.",
            "Standing DC readings across {stage} sit off target.",
        ],
        "bass_loss": [
            "LF response down; sweep shows the bottom end rolling off early.",
            "Low end missing on a swept tone, falling away below the midrange.",
            "Output thin; bass content not coming through on program.",
            "Frequency response rolls off at the low end.",
            "Bottom octaves down on the analyser relative to the mids.",
            "Kick and bass guitar lack weight at line out; sounds thin.",
            "Low-frequency response down compared with a reference unit.",
            "Bass rolled off at line out; full-range program comes back lean.",
        ],
        "treble_loss": [
            "HF response down; sweep falls away early at the high end.",
            "Top end rolled off; output sounds dull on program.",
            "Highs attenuated relative to midband on a swept tone.",
            "Muffled output; treble not coming through.",
            "Response droops at the high-frequency end on the analyser.",
            "Top octave missing; cymbals and sibilance dulled on the monitors.",
            "Against a reference unit, high-frequency content at line out is down.",
            "Treble end of the sweep sags; output sounds dark and closed-in.",
        ],
        "closer": [
            "",
            "Awaiting customer approval before proceeding.",
            "Quote to follow.",
            "Further checks pending; will update the ticket.",
            "Customer wants it back by end of week.",
            "Parked on the shelf until the estimate is signed off.",
            "Logged by the day shift.",
            "Return shipping label is in the box.",
        ],
    },
    "hobbyist": {
        "opener": [
            "Hey all, long-time lurker, first real post here.",
            "So I picked up a secondhand channel strip at a swap meet and I've been "
            "tinkering with it since.",
            "Bit of background first: this is a single-channel preamp strip I built "
            "from a kit a couple of years back.",
            "Hoping someone here can help me out with a mono channel strip I bought "
            "off an auction site.",
            "Evening folks, I've got a rackmount channel strip on my kitchen table and "
            "could use a second pair of eyes.",
            "Right, so I'm a hobbyist, not a pro, and I've inherited a studio channel "
            "strip from a mate.",
            "Hi everyone, hope this is the right subforum for a question about a channel strip.",
            "Long story, but I ended up with a used one-channel strip from a studio clear-out.",
        ],
        "no_output": [
            "Thing is, it passes no sound at all, nothing comes out the back of it.",
            "I plug a mic or a synth in and get absolutely nothing at the output, total silence.",
            "It powers up okay but there's no audio coming through whatsoever, like the "
            "signal vanishes somewhere inside.",
            "No output at all. I've tried different cables and inputs on my interface and "
            "it's just silent.",
            "Whatever I feed into it, nothing comes out the other end, not a peep.",
            "The channel is completely dead audio-wise, even though it switches on and looks normal.",
            "Signal goes in and that's the end of it, I get zero at the output no matter "
            "what I twiddle.",
            "It's gone mute on me, not a sound out of it whatever I do.",
        ],
        "low_gain": [
            "The output's quieter than it should be, I reckon about {db} dB down going by "
            "my DAW meters.",
            "Compared to my other preamp it comes out roughly {db} dB lower with the same settings.",
            "I have to bring the track up something like {db} dB more than normal to get "
            "a usable level.",
            "Level seems low, maybe {db} dB or thereabouts under where it used to sit.",
            "Ran a test tone through it and the output came back around {db} dB lower "
            "than I'd expect.",
            "The level coming out is lower than it used to be, and I have to turn things "
            "up to compensate.",
            "It's just not as loud as it should be, the gain seems to have dropped off.",
            "Feels like it's lost some gain, everything comes out weaker than my other gear.",
        ],
        "hum": [
            "There's a hum in the background all the time, sounds like mains noise, even "
            "with nothing plugged in.",
            "I'm getting a low buzz on the output, sort of a 60 cycle thing, that doesn't "
            "change with the gain.",
            "Constant low-pitched drone underneath everything, like standing next to a fridge.",
            "It picks up this mains hum that you can hear in the headphones as soon as it's "
            "switched on.",
            "There's a steady low-frequency buzz coming out of it, and moving it to a different "
            "outlet makes no difference.",
            "Behind the audio there's a hum at mains frequency, 50 Hz by the sound of it.",
            "Sounds like that classic cheap-guitar-amp hum, right there on the output.",
            "I can hear a 120 Hz-ish buzz sitting under the signal the whole time.",
        ],
        "distortion": [
            "Everything sounds distorted and fuzzy even at normal levels, like it's being "
            "overdriven.",
            "Vocals come out gritty and broken up, and I'm nowhere near pushing the gain.",
            "It's clipping on material that should be clean, sounds crunchy and harsh.",
            "A clean guitar DI comes out with a raspy, overdriven edge, which is new for this unit.",
            "I put a sine wave through and it looks squashed and flattened on my cheap scope, "
            "and it sounds dirty too.",
            "Even at sensible levels the sound breaks up, sort of a gritty distortion on the peaks.",
            "The output is distorted, like a fuzz pedal is switched on somewhere in the chain.",
            "Anything I run through it comes out sounding dirty and saturated when it should "
            "be clean.",
        ],
        "dc_at_output": [
            "Whenever I plug the output into my interface I get a thump, and there's a pop "
            "at switch-on too.",
            "My multimeter shows DC sitting on the output, which I'm pretty sure shouldn't be there.",
            "Every time I patch it in there's this thud through the monitors, and the meter "
            "says there's DC on the output.",
            "There's a pop through the speakers whenever I connect or disconnect it, which "
            "I gather means DC at the output.",
            "I noticed my speaker cone sitting pushed out when this unit is connected, and I "
            "measured DC on the output.",
            "Switching it on or off sends a thump through the whole system, which never used "
            "to happen.",
            "There's DC coming out of it; my meter reads a steady voltage on the output with "
            "nothing playing.",
            "Plugging and unplugging the output gives a pop every single time, which is new.",
        ],
        "bias_drift": [
            "I went round with my multimeter and the DC voltages in {stage} don't match what "
            "the schematic says.",
            "Measured the operating voltages around {stage} and they're off from what the "
            "build notes list.",
            "Something is up with the bias in {stage}, the voltages I'm reading don't "
            "match the spec.",
            "Probing around {stage} with my meter, the DC readings don't line up with the "
            "service manual.",
            "When I check the idle voltages on {stage}, they're not where they're supposed to be.",
            "According to my meter, the steady-state voltages inside {stage} are sitting in the "
            "wrong place.",
            "I did a voltage check and it looks like {stage} has its DC conditions out of whack.",
            "Comparing against the kit's voltage chart, the readings for {stage} are off.",
        ],
        "bass_loss": [
            "The bottom end has kind of disappeared, everything sounds thin and weedy.",
            "Bass guitar and kick come through lacking their low end, as if a high-pass "
            "filter got switched in.",
            "It sounds tinny now, the lows just aren't there anymore.",
            "Low frequencies seem to be rolled off, my bass synth patches sound lightweight.",
            "Everything has lost its weight, the low end is missing compared to how it used "
            "to sound.",
            "I ran a sweep and the response falls away at the bass end.",
            "There's no warmth or bottom to the sound any more, it's gone thin.",
            "Next to my other preamp it sounds lean, like the low frequencies have been cut away.",
        ],
        "treble_loss": [
            "The top end has gone missing, everything sounds dull and muffled.",
            "It sounds like there's a blanket over the speakers, no sparkle or air.",
            "Highs seem rolled off, cymbals and hi-hats have lost their shimmer.",
            "Vocals have lost their clarity up top, sibilance and breath sounds are just gone.",
            "When I swept it with a tone generator the output fell off as I went up in frequency.",
            "Everything sounds darker than it should, the treble just isn't there.",
            "Acoustic guitar sounds muffled, like it's coming from the next room.",
            "There's no crispness left, the high frequencies seem to be getting lost somewhere.",
        ],
        "closer": [
            "",
            "Any pointers much appreciated!",
            "Cheers in advance, and sorry for the wall of text.",
            "I'll post an update if I get anywhere with it.",
            "Happy to post photos or more details if that helps.",
            "I've gotten great help on this forum before, so fingers crossed.",
            "Would love to get this back in service before my next recording project.",
            "Let me know if there's anything specific I should be checking.",
        ],
    },
    "studio_client": {
        "opener": [
            "Hi, I run a small recording studio and one of our channel strips needs looking at.",
            "Hello, I'm a singer-songwriter and I use this single-channel preamp unit for most "
            "of my vocals.",
            "Hi there, I'd like to book in one of our rack units for a repair.",
            "Good morning, we have a channel strip at our studio that I'd like you to take a "
            "look at.",
            "Hey, I'm not technical at all, so bear with me, but I have a channel strip I use "
            "every day.",
            "Hi, this is about the channel strip we bought a few years ago for our tracking room.",
            "Hello, our studio manager asked me to get in touch about one of our preamp units.",
            "Hi, I record podcasts and voiceovers at home using a channel strip in a small rack.",
        ],
        "no_output": [
            "Nothing comes out of it anymore; it switches on, but there's no sound at all.",
            "When I sing into the mic I get complete silence, not a thing on my recordings.",
            "It's totally silent, no audio comes through it whatever I plug in.",
            "It turns on but doesn't pass any sound; everything else works when I take it "
            "out of the chain.",
            "My vocals just disappear when they go through this unit, there's nothing coming out.",
            "It has stopped making any sound whatsoever.",
            "I get nothing out of it at all, the track stays empty when I record through it.",
            "The unit has gone mute, no sound makes it out the other side.",
        ],
        "low_gain": [
            "It's quieter than it used to be, and my engineer says it's about {db} dB lower "
            "than it should be.",
            "I have to turn it up roughly {db} dB more than usual in my recording software to "
            "get the same loudness.",
            "A technician friend checked it and told me the volume is down by around {db} dB.",
            "Our producer says it comes out something like {db} dB softer than our other "
            "channel strip.",
            "The person who set up our studio measured it and said it's {db} dB or so down "
            "on volume.",
            "The volume coming out of it has dropped, I have to turn everything up to hear "
            "it properly.",
            "It sounds weaker than before, like it's lost some of its loudness.",
            "My voice comes through quieter than it should, even when I turn the unit up.",
        ],
        "hum": [
            "There's a humming noise in the background all the time, even when nobody is playing.",
            "I can hear a low buzz coming through the speakers whenever it's switched on.",
            "It makes a constant low droning sound underneath everything I record.",
            "There's an electrical hum on every take; you can hear it in the gaps between phrases.",
            "A deep buzzing sound sits under my vocals the whole time.",
            "Between takes you can hear a low, steady hum through the monitors.",
            "It's picking up a buzz that sounds like a fluorescent light, low and steady.",
            "Everything I record has a background drone to it, rather like an old air conditioner.",
        ],
        "distortion": [
            "My vocals come out sounding distorted and crunchy, even when I'm singing softly.",
            "Everything sounds fuzzy and broken up, like a speaker that's been pushed too hard.",
            "It makes clean instruments come out dirty and harsh, as if the audio is breaking up.",
            "There's a gritty, overdriven quality on everything, even at normal volume.",
            "Notes come out torn and ragged, as if they're being chewed up, even when I'm not "
            "pushing it.",
            "The sound is dirty, like an old radio that's been turned up too far.",
            "My acoustic guitar comes out with a raspy, distorted edge it never used to have.",
            "Everything that goes through it sounds grainy and distorted.",
        ],
        "dc_at_output": [
            "Whenever I plug it in or unplug it, there's a thump through my speakers.",
            "Switching it on makes a pop come out of the monitors, and it does it again when I "
            "turn it off.",
            "Every time I change the patching there's a thud that makes me worry about my speakers.",
            "My speakers go 'thump' when I connect this unit, which none of my other gear does.",
            "It pops through the whole system whenever it's powered up or down.",
            "When it's connected, one of my speaker cones sits pushed forward, and there's a "
            "thump each time I plug it in.",
            "There's a pop every time I turn it on, and another whenever I patch it into the desk.",
            "My tech said there's DC on the output, and I get a thump every time I connect it.",
        ],
        "bias_drift": [
            "The technician who looked at it told me the voltages in {stage} are wrong.",
            "A repair guy measured it and said something in {stage} isn't running at the "
            "right voltage.",
            "My engineer put a meter on it and said the readings around {stage} aren't what "
            "they should be.",
            "I was told by a tech that the DC levels in {stage} are off.",
            "Someone who knows electronics checked inside and said {stage} isn't sitting at "
            "the correct voltages.",
            "Our studio tech measured {stage} and told me the operating voltages there don't "
            "match the manual.",
            "According to the last person who serviced it, the voltages around {stage} have "
            "gone out of range.",
            "A friend who fixes amplifiers took some readings and reckons the voltages inside "
            "{stage} aren't where they ought to be.",
        ],
        "bass_loss": [
            "It sounds thin now, the low end has gone missing.",
            "My bass guitar sounds tinny through it, with no depth.",
            "The deep, warm lows have disappeared from everything I record.",
            "Kick drums don't have any boom anymore, it all sounds lightweight.",
            "My voice sounds thin, like the body has been taken out of it.",
            "There's no bottom end, it sounds like listening on a cheap phone speaker.",
            "The bass has faded out of the sound, it's lost its weight.",
            "Everything feels light and thin, without the richness at the bottom it used to have.",
        ],
        "treble_loss": [
            "It sounds muffled, like there's a pillow over the speaker.",
            "The sound has gone dull and dark, no brightness or sparkle.",
            "My vocals have lost their crispness, they sound like they're coming from behind "
            "a curtain.",
            "Cymbals and shakers have lost their shine and sound woolly.",
            "The treble seems to have vanished, and everything sounds murky.",
            "It's like listening through a wall; the sizzle on top has gone.",
            "Everything sounds like it's underwater, no clarity on top.",
            "My recordings through it come out darker than they should, the air and shimmer "
            "have gone.",
        ],
        "closer": [
            "",
            "Please let me know roughly what it would cost to fix.",
            "We have sessions booked next week, so sooner would be better.",
            "Thanks so much for your help.",
            "Can you give me a rough quote and turnaround time?",
            "I can drop it off whenever suits you.",
            "It's our main vocal chain, so we'd love to have it back soon.",
            "Feel free to call me if you need any more information.",
        ],
    },
}

SEVERITY_TAG_B: dict[str, dict[str, str]] = {
    "bench_tech": {
        "mild": " Minor, but repeatable.",
        "moderate": "",
        "severe": " Severe; obvious straight away.",
    },
    "hobbyist": {
        "mild": " It's fairly subtle to be honest, but it's there.",
        "moderate": "",
        "severe": " And honestly it's about as bad as it gets.",
    },
    "studio_client": {
        "mild": " It's fairly minor, though.",
        "moderate": "",
        "severe": " It's really bad, honestly.",
    },
}
