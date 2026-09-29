"""What a technician's free text may record (red team, rounds 5 and 6).

Safety records (how a high-voltage unit was first powered, the owner's approval to remove
parts, the discharge readings before a part is lifted, a trainee's supervisor) never come
from free text: the offline chat and the live model's tool calls cannot make them, only
the app's forms can (the server's structured endpoints). Round 5 read attestations from
chat under rules for plain affirmative statements; round 6 still found hearsay, quoted
text, retractions and the tool's own instructions accepted, so the chat path was removed.

Free text may still carry a diagnostic reading ("TP4 12.3 V"). It counts only as a plain
affirmative statement: a question, negation, condition, plan or guess records nothing.
"""

from __future__ import annotations

import re

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


# Readings that are not the technician's own measurement now (red team, M2 round 1):
# someone else's, a document's, an old one, or a voltage that is not at a test point.
_REPORTED = re.compile(
    r"\b(colleague|co-?worker|owner|customer|client|friend|boss|someone|somebody|previous tech\w*|"
    r"last tech\w*|other tech\w*|my (?:tech|mate|buddy|dad|brother|son|husband|wife))\b"
    r"|\b(said|says|told|according to|reportedly|apparently|supposedly|quoted)\b"
    r"|\b(he|she|they) (?:measured|read|got|found|saw|reported|wrote|checked)\b",
    re.I,
)
_DOCUMENT = re.compile(
    r"\b(schematic|manual|chart|spec\w*|datasheet|label|diagram|drawing|nameplate|marking)s?\s+"
    r"(?:shows?|says?|lists?|gives?|specif\w*|calls? for|reads?|states?|indicates?|has|is)\b"
    r"|\b(?:nominal|rated|supposed to be|meant to be)\b",
    re.I,
)
_PAST = re.compile(
    r"\b(last (?:week|month|year|time|visit)|yesterday|earlier today|years? ago|before it "
    r"(?:broke|failed|died)|when it (?:was )?(?:still )?work\w*|used to)\b",
    re.I,
)
_ELSEWHERE = re.compile(
    r"\b(wall (?:outlet|socket)|outlet|power strip|extension (?:cord|lead)|mains|heater|filament|"
    r"meter'?s? battery|battery|bench supply)\b",
    re.I,
)


def reported(text: str) -> str | None:
    """Why a typed reading is not the technician's own measurement at a test point, or None."""
    if _REPORTED.search(text):
        return "someone else's reading"
    if _DOCUMENT.search(text):
        return "a value from a document, not a measurement"
    if _PAST.search(text):
        return "an earlier reading, not one taken now"
    if _ELSEWHERE.search(text):
        return "a voltage that is not at a test point"
    return None


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


NUMBER = r"[-+]?\d+(?:\.\d+)?"
VOLT_UNIT = r"(?:kilo|milli|micro|[kmuµ])?(?:volts?|vdc|v)(?![a-z])"


def volts(num: str, unit: str | None) -> float:
    u = (unit or "v").lower()
    scale = (1e3 if u.startswith(("kilo", "k")) else 1e-3 if u.startswith(("milli", "m"))
             else 1e-6 if u.startswith(("micro", "u", "µ")) else 1.0)
    return float(num) * scale
