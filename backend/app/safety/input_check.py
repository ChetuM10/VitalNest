"""Rule-based input safety check, run before any retrieval or LLM call (decision G7).

Order of precedence: self-harm, emergency, diagnosis, dosing, prescription, out-of-scope.
Rules are regular expressions over a normalised message. They are deliberately blunt: they
catch common phrasings, miss paraphrases and other languages, and prefer showing emergency
guidance to missing an emergency. They do not guarantee medical safety (see docs/safety.md).
"""
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from app.safety import messages


class Category(str, Enum):
    EMERGENCY = "emergency"
    SELF_HARM = "self_harm"
    DIAGNOSIS = "diagnosis"
    DOSING = "dosing"
    PRESCRIPTION = "prescription"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass(frozen=True)
class InputCheckResult:
    status: Literal["ok", "emergency", "refused"]
    category: Category | None = None
    response: str | None = None

    @property
    def allowed(self) -> bool:
        return self.status == "ok"


def _compile(*patterns: str) -> list[re.Pattern]:
    return [re.compile(pattern) for pattern in patterns]


SELF_HARM = _compile(
    r"\b(?:kill|hurt|harm|injure) myself\b",
    r"\bend (?:my (?:own )?life|it all)\b",
    r"\btak(?:e|ing) my own life\b",
    r"\bcommit(?:ting)? suicide\b",
    r"\b(?:i'm|i am|im|feel|feeling|am) (?:\w+ ){0,2}suicidal\b",
    r"\b(?:think|thinking|thought|thoughts) (?:about|of) (?:suicide|killing myself|ending my life|self[- ]harm)\b",
    r"\b(?:don't|do not|dont) want to (?:live|be alive|be here|exist|wake up)\b",
    r"\bwant to die\b|\bwish i (?:was|were) dead\b|\bbetter off (?:dead|without me)\b",
    r"\b(?:cut|cutting|burn|burning|starve|starving) myself\b|\bself[- ]harming\b",
)

# Phrases that describe something happening now, so no extra context is needed.
EMERGENCY_ALWAYS = _compile(
    r"\b(?:can't|cant|cannot|can not|unable to) breathe\b",
    r"\b(?:not|stopped|stops|isn't|wasn't) breathing\b",
    r"\b(?:struggling|gasping) (?:to|for) breath(?:e)?\b",
    r"\b(?:is|are|am|just|has|was|went|become|became) (?:\w+ )?(?:unconscious|unresponsive)\b",
    r"\bhaving (?:a |an )?(?:heart attack|stroke|seizure|allergic reaction|asthma attack)\b",
    r"\b(?:overdosed|over dosed)\b|\b(?:i'm|i am|im) overdosing\b",
    r"\b(?:took|taken|swallowed|ate|drank) too (?:many|much)\b",
    r"\bswallowed (?:bleach|poison|chemicals?|detergent|batter(?:y|ies)|a battery)\b",
    r"\bbleeding\b.{0,25}\b(?:won't|will not|not stopping|doesn't stop)\b",
    r"\b(?:won't|will not|doesn't|does not) stop bleeding\b",
    r"\bcall (?:an |the )?ambulance\b|\bcall (?:911|999|112|108)\b",
    r"\b(?:i'm|i am|im) dying\b",
)

# Symptoms that are urgent when they are happening to the person asking (or someone they name).
EMERGENCY_CONTEXTUAL = _compile(
    r"\bchest (?:pain|pains|pressure|tightness)\b|\bpain in (?:my|his|her|the) chest\b",
    r"\b(?:shortness of breath|short of breath|trouble breathing|difficulty breathing|hard to breathe)\b",
    r"\b(?:face|smile|mouth) (?:is |has )?(?:drooping|droopy|drooped)\b|\bslurred speech\b",
    r"\bsudden(?:ly)? (?:numbness|weakness|confusion|loss of vision)\b",
    r"\bchoking\b|\b(?:passed out|collapsed|fainted)\b",
    r"\b(?:throat|tongue|face|lips) (?:is |are )?(?:closing|swelling|swollen)\b",
)

PERSONAL = re.compile(
    r"\b(?:i|i'm|im|i've|ive|my|me|we|our|he|she|they|he's|she's|they're|his|her|their|"
    r"someone|somebody|patient|baby|child|kid|son|daughter|mom|dad|mother|father|husband|wife|"
    r"friend|toddler)\b"
)
PAST_ONLY = re.compile(r"\b(?:last (?:year|month|week)|years? ago|months? ago|weeks? ago|ago|in the past|history of)\b")
CURRENT = re.compile(r"\b(?:right now|now|currently|at the moment|just now|still|ongoing)\b")

DIAGNOSIS = _compile(
    r"\bdo i have (?!to\b)",
    r"\b(?:could|might) i (?:possibly |actually )?have\b",
    r"\bdo you think i (?:have|am|might)\b",
    r"\bdiagnose (?:me|my|this|these)\b",
    r"\bwhat(?:'s| is) wrong with me\b",
    r"\bwhat (?:disease|condition|illness|infection|disorder|sickness)s? do i have\b",
    r"\bwhat (?:do|could|might) i have\b",
    r"\bam i (?:pregnant|sick|ill|dying|diabetic|depressed|anemic|infected)\b",
    r"\bis (?:this|it|that|my \w+) (?:cancer|a tumou?r|an infection|infected|diabetes|an allergy)\b",
)

DOSING = _compile(
    r"\bdosage(?! forms?\b)|\bdosing\b",
    r"\bwhat dose\b|\bdose of\b",
    r"\b(?:right|correct|safe|recommended|maximum|max|usual|normal|standard|adult|child|children's|child's) dose\b",
    r"\bhow (?:much|many) (?:\w+ ){0,3}(?:should|can|could|may|do|would) "
    r"(?:i|we|he|she|my \w+|a child|an adult|kids|children) (?:\w+ )?(?:take|give|inject|use|swallow|consume)\b",
    r"\bhow often (?:should|can|could|may|do) (?:i|we|he|she)(?: \w+)? (?:take|give|use|inject)\b",
    r"\b(?:take|give|inject|use|swallow) \d+(?:\.\d+)? ?(?:mg|mcg|µg|g|ml|iu|units?|tablets?|pills?|capsules?|drops?|puffs?)\b",
)

PRESCRIPTION = _compile(
    r"\bprescribe (?:me|us|him|her|something|a|an)\b|\bcan you prescribe\b",
    r"\b(?:write|give) (?:me |us )?(?:a )?prescription\b",
    r"\bwhat (?:should|can) i take for\b",
    r"\b(?:what|which) (?:medicine|medication|drug|pill|tablet|antibiotic|painkiller|ointment|cream|syrup|treatment)s?"
    r"(?: \w+)? (?:should|can|could|do|would) i (?:take|use|get|buy|try|start)\b",
    r"\b(?:should|can|could|may) i (?:stop|quit|skip|double|halve|switch|change|increase|reduce) (?:taking|using)\b",
    r"\b(?:stop|quit|skip|double|halve|change) my (?:\w+ ){0,2}(?:medication|medicine|meds|tablets|pills|dose|treatment|insulin|inhaler)\b",
)

OUT_OF_SCOPE = _compile(
    r"\bwrite (?:me |us )?(?:a |an |some |the )?(?:\w+ )?(?:poem|story|essay|song|joke|script|email|letter|code|program|function|haiku|limerick|speech)\b",
    r"\btell me a (?:joke|story)\b",
    r"\b(?:python|javascript|java|typescript|sql|html|css|c\+\+|bash) (?:code|script|function|program|query)\b",
    r"\btranslate (?:this|the following|that|these)\b",
    r"\b(?:bitcoin|crypto(?:currency)?|stock market|stock price|share price|forex)\b",
    r"\b(?:who (?:will win|won)|election|prime minister|president of)\b",
    r"\b(?:weather forecast|football score|cricket score|movie recommendations?)\b",
)

_REFUSALS = (
    (DIAGNOSIS, Category.DIAGNOSIS, messages.DIAGNOSIS_REFUSAL),
    (DOSING, Category.DOSING, messages.DOSING_REFUSAL),
    (PRESCRIPTION, Category.PRESCRIPTION, messages.PRESCRIPTION_REFUSAL),
    (OUT_OF_SCOPE, Category.OUT_OF_SCOPE, messages.OUT_OF_SCOPE_REFUSAL),
)


def normalise(text: str) -> str:
    """Lower-case, unify apostrophes and collapse whitespace so simple tricks do not hide a phrase."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    return re.sub(r"\s+", " ", text).strip()


def _any(patterns: list[re.Pattern], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _is_current_personal_emergency(text: str) -> bool:
    if not _any(EMERGENCY_CONTEXTUAL, text) or not PERSONAL.search(text):
        return False
    # "my mother had chest pain last year" is history, not an emergency; "...and right now" is.
    return not PAST_ONLY.search(text) or bool(CURRENT.search(text))


def check_input(message: str) -> InputCheckResult:
    text = normalise(message)

    if _any(SELF_HARM, text):
        return InputCheckResult("emergency", Category.SELF_HARM, messages.SELF_HARM_MESSAGE)

    if _any(EMERGENCY_ALWAYS, text) or _is_current_personal_emergency(text):
        return InputCheckResult("emergency", Category.EMERGENCY, messages.EMERGENCY_MESSAGE)

    for patterns, category, response in _REFUSALS:
        if _any(patterns, text):
            return InputCheckResult("refused", category, response)

    return InputCheckResult("ok")
