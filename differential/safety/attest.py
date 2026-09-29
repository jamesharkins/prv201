"""What a technician's free text may attest (red team, round 5).

The offline chat reads three attestations that unlock steps: how a high-voltage unit was
first brought up, the owner's approval to remove parts, and discharge readings before a
part is lifted. Each must be a plain, affirmative statement of fact. A question, a
negation, a condition, a plan or a guess records nothing, and a discharge reading counts
only when every number in the message is a voltage with its unit. When in doubt nothing
is recorded: the technician can always use the form or button, which take structured
values. The same rules guard the live model's tool calls (``agent._guarded_tool``).
"""

from __future__ import annotations

import re
from typing import Any

# Negations, including contractions (hasn't, can't, dont) and a few non-English ones.
_NEG = re.compile(
    r"\b(no|not|nope|nah|never|none|nobody|nothing|neither|nor|cannot|without|absent|"
    r"refus\w*|declin\w*|reject\w*|unavailable|unable|missing|broken|lost|skip\w*|instead|"
    r"rather|except|lack\w*|out on loan)\b"
    r"|\b\w+n['’]t\b|\b(cant|dont|wont|isnt|arent|wasnt|werent|hasnt|havent|hadnt|didnt|"
    r"doesnt|couldnt|wouldnt|shouldnt|aint)\b|\bn['’](?=\w)"
    r"|\b(pas|sans|jamais|rien|aucun\w*|sin|nunca|nada|nicht|kein\w*|ohne|nie|niet|geen|"
    r"nem|nao|não|non|ingen|ikke|inte)\b",
    re.I,
)
# Conditions, plans, guesses and hedges: none of them states what was done.
_MODAL = re.compile(
    r"\b(if|unless|would|could|should|might|may|maybe|perhaps|probably|possibly|presumably|"
    r"likely|unlikely|suppos\w*|assum\w*|hypothetic\w*|pretend|imagine|guess\w*|think|"
    r"believe|expect\w*|hope\w*|plan\w*|intend\w*|going to|gonna|will|shall|later|tomorrow|"
    r"soon|yet|wait\w*|hold|pending|until|once|want|wanna|need|about to|try\w*|ask\w*)\b"
    r"|\b(i|you|he|she|we|they|it|that|there|who)['’](d|ll)\b",
    re.I,
)
_QUESTION_START = re.compile(
    r"(?:^|[.!;:]\s*)(what|which|who|whom|whose|why|how|when|where|should|could|would|can|"
    r"may|might|shall|will|is|are|am|was|were|do|does|did|has|have|had)\b",
    re.I,
)


def uncertain(text: str) -> str | None:
    """Why ``text`` is not a plain affirmative statement, or None if it is."""
    if "?" in text:
        return "a question"
    if _QUESTION_START.search(text.strip()):
        return "a question"
    if _NEG.search(text):
        return "a negation"
    if _MODAL.search(text):
        return "a condition, plan or guess"
    return None


# ---------------------------------------------------------------- owner approval
_OWNER = re.compile(r"\b(owner|owner['’]s|customer|customer['’]s|client|client['’]s)\b", re.I)
_APPROVAL = re.compile(
    r"\b(approv\w*|agree\w*|consent\w*|ok['’]?d|okayed|authori[sz]\w*|signed off|permission|"
    r"gave (?:the )?go-?ahead|said (?:yes|ok|okay))\b",
    re.I,
)


def owner_approval(text: str) -> bool:
    """True only for an affirmative statement that the owner approved removing parts."""
    return bool(_OWNER.search(text) and _APPROVAL.search(text)) and uncertain(text) is None


# ---------------------------------------------------------------- bring-up
BRING_UP_RE: dict[str, re.Pattern[str]] = {
    "variac": re.compile(r"\bvariac|auto-?transformer|variable transformer", re.I),
    "series_lamp": re.compile(r"series[- ]?(?:lamp|bulb)|dim[- ]?bulb|light ?bulb|lamp limiter",
                              re.I),
    "current_limited_supply": re.compile(r"current[- ]limit\w*|bench supply|lab supply", re.I),
    "known_good": re.compile(r"already (?:running|working|on)|(?:was|been) (?:running|working|"
                             r"playing) (?:fine|normally|ok)|known[- ]good|worked (?:fine|normally)",
                             re.I),
}
_DID = re.compile(r"\b(brought|brung|used|using|powered|ran|running|started|fired|energi[sz]ed|"
                  r"came up|come up|hooked|connected|through|via|on (?:a|the|my) \w+|"
                  r"with (?:a|the|my) \w+)\b", re.I)
_FILLER = re.compile(r"\b(yes|yeah|yep|ok|okay|i|we|it|the|a|an|my|on|with|using|via|through|"
                     r"and|slowly|first|up|unit|amp|was|brought)\b|[.,!;:]", re.I)


def bring_up_method(text: str) -> str | None:
    """The bring-up method a message affirms, or None. Exactly one method must be named,
    the message must say it was used (or be a bare answer such as "on a variac"), and it
    must not be a question, negation, condition or plan."""
    if uncertain(text) is not None:
        return None
    hits = [m for m, rx in BRING_UP_RE.items() if rx.search(text)]
    if len(hits) != 1:
        return None
    method = hits[0]
    if method == "known_good":
        return method
    rest = _FILLER.sub(" ", BRING_UP_RE[method].sub(" ", text))
    if _DID.search(text) or not rest.strip():
        return method
    return None


# ---------------------------------------------------------------- discharge readings
NUMBER = r"[-+]?\d+(?:\.\d+)?"
VOLT_UNIT = r"(?:kilo|milli|micro|[kmuµ])?(?:volts?|vdc|v)(?![a-z])"
_TP_READING = re.compile(rf"\b(?P<tp>TP\d+)\b[^\d\n]{{0,12}}?(?P<num>{NUMBER})\s*(?P<unit>{VOLT_UNIT})",
                         re.I)
_ANY_NUMBER = re.compile(rf"(?<![A-Za-z\d.])(?P<num>{NUMBER})(?P<after>\s*[A-Za-zµ]*)")


def volts(num: str, unit: str | None) -> float:
    u = (unit or "v").lower()
    scale = (1e3 if u.startswith(("kilo", "k")) else 1e-3 if u.startswith(("milli", "m"))
             else 1e-6 if u.startswith(("micro", "u", "µ")) else 1.0)
    return float(num) * scale


def discharge_readings(text: str) -> dict[str, Any]:
    """Discharge readings in a message, as ``confirm_discharge`` arguments.

    Accepted: "TP4 0.3 V, TP5 0.2 V", or one voltage for the main filter capacitor
    ("0.4 V"), or one voltage for every point ("all points 0.3 V"). Refused with a reason:
    a question, negation, condition or guess; a comma decimal; any number that is not a
    voltage with its unit (a duration, a wattage, a count, a resistor value). Returns {}
    when the message holds no reading at all."""
    numbers = list(_ANY_NUMBER.finditer(text))
    if not numbers:
        return {}
    why = uncertain(text)
    if why is not None:
        return {"error": f"that reads as {why}; report the voltages you measured, for example "
                         "\"TP4 0.3 V, TP5 0.2 V\", or use the discharge form"}
    if re.search(r"\d,\d", text):
        return {"error": "write readings with a decimal point, for example 0.5 V"}
    for m in numbers:
        after = m.group("after").strip()
        if not re.fullmatch(VOLT_UNIT, after, re.I):
            return {"error": "give only the voltages you measured, each with its unit "
                             "(for example TP4 0.3 V); other numbers are not read as readings"}
    pairs: dict[str, float] = {}
    for m in _TP_READING.finditer(text):
        tp = m.group("tp").upper()
        pairs[tp] = max(pairs.get(tp, 0.0), abs(volts(m.group("num"), m.group("unit"))))
    if pairs:
        if len(pairs) != len(numbers):
            return {"error": "give one voltage per test point (for example TP4 0.3 V, TP5 0.2 V)"}
        return {"readings": pairs}
    if len(numbers) != 1:
        return {"error": "give one voltage per test point (for example TP4 0.3 V, TP5 0.2 V)"}
    m = numbers[0]
    v = volts(m.group("num"), m.group("after").strip())
    return {"volts": v, "all_points": bool(re.search(r"\b(all|every|each)\b", text, re.I))}


# ---------------------------------------------------------------- supervisor
_SUPERVISOR = [
    re.compile(r"\bsupervis(?:or|ing|ed)\b(?:\s+(?:today|here|now))?\s*(?:is|:|=|-|by)\s+"
               r"(?P<name>[A-Za-z][A-Za-z .'-]{1,60})", re.I),
    re.compile(r"\b(?P<name>[A-Z][a-z]+(?: [A-Z][a-z.'-]+){0,3}) is (?:my |the |our )?"
               r"supervis\w*", re.I),
]


def supervisor_name(text: str) -> str | None:
    """A supervisor's name stated affirmatively in a message ("my supervisor is Ana Ruiz",
    "supervised by Ana Ruiz"), or None."""
    if uncertain(text) is not None:
        return None
    for rx in _SUPERVISOR:
        m = rx.search(text)
        if m:
            return m.group("name").strip(" .'-")
    return None
