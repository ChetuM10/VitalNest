"""Streaming output guardrail (decision D1 = B): check the model's answer sentence by sentence and
release only approved sentences to the user.

Like the input check this is rule-based and blunt. It catches common unsafe patterns (doses and
schedules, diagnoses, instructions to stop or change medicine, prescribing) and will miss
paraphrases. A sentence that is only unsafe in combination with several others can also slip
through. It does not guarantee medical safety (see docs/safety.md).
"""
import re
from dataclasses import dataclass
from enum import Enum

from app.llm.output_format import SUGGESTIONS_MARKER
from app.safety.input_check import normalise


class OutputIssue(str, Enum):
    DOSAGE = "dosage"
    DIAGNOSIS = "diagnosis"
    MEDICATION_CHANGE = "medication_change"
    PRESCRIBING = "prescribing"


@dataclass(frozen=True)
class OutputCheck:
    allowed: bool
    issue: OutputIssue | None = None


# ---------- rules ----------

_UNIT = r"(?:mg|mcg|µg|g|ml|iu|units?)"
_AMOUNT = rf"\d+(?:\.\d+)?\s?{_UNIT}\b"
_FORM = r"(?:tablets?|pills?|capsules?|drops?|puffs?|teaspoons?|tablespoons?|sachets?)"
_COUNT = r"(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|half)"
_GIVE = r"(?:take|taking|takes|give|giving|administer|inject|swallow|use)"

_TAKE_AMOUNT = re.compile(rf"\b{_GIVE}\b[^\n]{{0,40}}?\b(?:{_AMOUNT}|{_COUNT}\s+{_FORM}\b)")
_DOSE_AMOUNT = re.compile(rf"\b(?:dose|doses|dosage|dosing)\b[^\n]{{0,40}}?{_AMOUNT}|{_AMOUNT}[^\n]{{0,25}}?\b(?:dose|dosage)\b")
_SCHEDULE = re.compile(
    r"\b(?:once|twice|three times|four times|\d+ times|every \d+(?:-\d+)? (?:hours?|days?|weeks?)|"
    r"every (?:morning|night|evening)|at bedtime|before bed(?:time)?|daily|per day|a day|each day)\b"
)
_AMOUNT_RE = re.compile(_AMOUNT)
# Medicine forms only: "1 teaspoon of salt a day" is food advice, not a dose.
_COUNT_FORM = re.compile(rf"\b{_COUNT}\s+(?:tablets?|pills?|capsules?|drops?|puffs?)\b")
_MEDICINE_CUE = re.compile(
    r"\b(?:take|taking|give|dose|doses|dosage|medicine|medicines|medication|medications|drug|drugs|"
    r"tablets?|pills?|capsules?|ibuprofen|paracetamol|acetaminophen|aspirin|antibiotics?|painkillers?|insulin)\b"
)

_DIAGNOSIS = [re.compile(p) for p in (
    r"\byou (?:probably|likely|definitely|certainly|clearly|most likely) (?:have|are suffering from|suffer from|got)\b",
    r"\b(?:sounds|looks|seems) like you (?:have|are suffering|may have|might have|probably have)\b",
    r"\byou(?: are|'re) suffering from\b|\byou suffer from\b",
    r"\byour symptoms (?:indicate|suggest|mean|point to|show)\b",
    r"\b(?:this|that|it) is (?:definitely|certainly|clearly|most likely|probably) "
    r"(?!caused\b|due\b|related\b|linked\b|safe\b|best\b|not\b|to\b|an? (?:symptom|sign)\b)\w",
    r"\bi (?:think|believe|suspect) you (?:have|are)\b|\bi (?:can )?diagnose\b",
    r"\bbased on your (?:symptoms|description|answers),? you (?:have|are|may have|might have)\b",
)]

_NOUNS = r"(?:medication|medicine|medicines|meds|tablets|pills|dose|dosage|treatment|insulin|inhaler|prescription|antibiotics?)"
_MED_STOP = re.compile(rf"\b(?:stop|discontinue|quit|skip|halve|double)\b(?: taking| using)? (?:your|the|any) (?:\w+ ){{0,3}}{_NOUNS}\b")
_MED_ADJUST = re.compile(rf"\b(?:increase|reduce|change)\b(?: taking| using)? your (?:\w+ ){{0,2}}{_NOUNS}\b")
# "...go away after you stop taking the medicine" describes what happens; it is not an instruction.
_DESCRIPTIVE_PREFIX = re.compile(r"\b(?:after|once|when|whenever|until|if|unless) (?:you|your|they|a person|someone|your child)\s*$")
# Advice that keeps the decision with the person's clinician is allowed, e.g. "do not stop without asking".
_SAFE_QUALIFIER = re.compile(
    r"\b(?:do not|don't|never|without (?:first )?(?:talking|speaking|checking|consulting|asking)|"
    r"before (?:you )?(?:stop|chang|skip|reduc|increas)\w*|talk to your|ask your|check with your|"
    r"unless your (?:doctor|provider)|your (?:doctor|provider|health care provider|healthcare provider) "
    r"(?:may|might|will|can|should) )\b"
)

_PRESCRIBING = [re.compile(p) for p in (
    r"\bi (?:recommend|suggest|advise|prescribe)\b[^.!?\n]{0,15}\byou\b[^.!?\n]{0,15}\b(?:take|use|start|try)\b",
    r"(?<!if )(?<!when )(?<!whether )\byou (?:should|must|need to|ought to) (?:take|use|start|try) (?:an? |some |the )?(?:\w+ ){0,2}"
    # Named drugs and drug classes only: "you must take insulin" in a description of type 1 diabetes
    # is education, whereas "you should take paracetamol for the pain" is a recommendation.
    r"(?:ibuprofen|paracetamol|acetaminophen|aspirin|naproxen|antibiotics?|painkillers?|steroids?)\b",
)]


def _medication_change(text: str) -> bool:
    if _SAFE_QUALIFIER.search(text):
        return False
    return any(
        not _DESCRIPTIVE_PREFIX.search(text[:match.start()])
        for pattern in (_MED_STOP, _MED_ADJUST)
        for match in pattern.finditer(text)
    )


def _issue(text: str) -> OutputIssue | None:
    if (
        _TAKE_AMOUNT.search(text)
        or _DOSE_AMOUNT.search(text)
        or (_SCHEDULE.search(text) and (_COUNT_FORM.search(text) or (_AMOUNT_RE.search(text) and _MEDICINE_CUE.search(text))))
    ):
        return OutputIssue.DOSAGE
    if _medication_change(text):
        return OutputIssue.MEDICATION_CHANGE
    if any(pattern.search(text) for pattern in _PRESCRIBING):
        return OutputIssue.PRESCRIBING
    if any(pattern.search(text) for pattern in _DIAGNOSIS):
        return OutputIssue.DIAGNOSIS
    return None


def check_sentence(sentence: str, previous: str = "") -> OutputCheck:
    """Check one sentence. `previous` is the sentence before it, which already passed on its own.

    A dosage can be split across two sentences ("Take this medicine." then "500 mg twice a day."),
    so the take-then-amount rules are also run on the pair, but only a match that ends inside the
    new sentence counts: the previous sentence alone was already fine.
    """
    text = normalise(sentence)
    issue = _issue(text)
    if issue is None and previous:
        before = normalise(previous)
        combined = f"{before} {text}"
        for pattern in (_TAKE_AMOUNT, _DOSE_AMOUNT):
            match = pattern.search(combined)
            if match and match.end() > len(before) + 1:
                issue = OutputIssue.DOSAGE
                break
    return OutputCheck(allowed=issue is None, issue=issue)


# ---------- sentence splitting ----------

_BOUNDARY = re.compile(r"(?<=[.!?])[\"')\]]*\s+|[ \t]*\n\s*")
_ALWAYS_ABBREVIATIONS = {"dr.", "mr.", "mrs.", "ms.", "prof.", "st.", "jr.", "sr.", "no.", "fig."}
_USUALLY_ABBREVIATIONS = {"e.g.", "i.e.", "etc.", "vs.", "approx."}


def split_complete_sentences(text: str) -> tuple[list[tuple[str, str]], str]:
    """Split off the sentences that are certainly finished.

    Returns ([(sentence, separator), ...], remainder). A full stop at the very end of the text is
    not certain yet (the next characters might be digits or an abbreviation), so it stays in the
    remainder. Joining every sentence+separator and the remainder gives back the original text.
    """
    sentences: list[tuple[str, str]] = []
    start = 0
    for match in _BOUNDARY.finditer(text):
        separator = match.group(0)
        if "\n" not in separator:
            following = text[match.end():match.end() + 1]
            if not following:
                continue  # cannot tell yet
            last_word = text[start:match.start()].split()[-1:] or [""]
            word = last_word[0].casefold()
            if word in _ALWAYS_ABBREVIATIONS or (word in _USUALLY_ABBREVIATIONS and following.islower()):
                continue
        sentences.append((text[start:match.start()], separator))
        start = match.end()
    return sentences, text[start:]


def _partial_marker_length(text: str, marker: str) -> int:
    """Length of the longest ending of `text` that is the start of `marker` (but not all of it)."""
    for length in range(min(len(marker) - 1, len(text)), 0, -1):
        if marker.startswith(text[-length:]):
            return length
    return 0


# ---------- stream guard ----------

class StreamGuard:
    """Feed it the model's text as it arrives; it returns only text that passed the checks.

    After `blocked` becomes true nothing more is released and the caller should cancel the model
    stream. Text after the suggestions marker is collected in `suggestions_raw`, never released.
    """

    def __init__(self, max_buffer: int = 300, marker: str = SUGGESTIONS_MARKER, checker=check_sentence) -> None:
        self._max_buffer = max_buffer
        self._marker = marker
        self._checker = checker
        self._buffer = ""
        self._previous = ""
        self._in_suggestions = False
        self.blocked = False
        self.block_reason: OutputIssue | None = None
        self.suggestions_raw = ""

    def feed(self, chunk: str) -> list[str]:
        if self.blocked:
            return []
        if self._in_suggestions:
            self.suggestions_raw += chunk
            return []
        text = self._buffer + chunk
        position = text.find(self._marker)
        if position != -1:
            self._in_suggestions = True
            self.suggestions_raw = text[position + len(self._marker):]
            self._buffer = ""
            return self._release(text[:position], final=True)
        held = _partial_marker_length(text, self._marker)  # might be the start of the marker
        released_part, tail = text[:len(text) - held], text[len(text) - held:]
        output = self._release(released_part, final=False)
        self._buffer += tail
        return output

    def finish(self) -> list[str]:
        if self.blocked or self._in_suggestions:
            return []
        text, self._buffer = self._buffer, ""
        held = _partial_marker_length(text, self._marker)
        if held >= 3:  # the stream stopped in the middle of the marker: drop the fragment
            text = text[:len(text) - held]
        return self._release(text, final=True)

    # ---- internals ----

    def _approve(self, sentence: str) -> bool:
        stripped = sentence.strip()
        if not stripped:
            return True
        result = self._checker(stripped, previous=self._previous)
        if not result.allowed:
            self.blocked, self.block_reason = True, result.issue
            self._buffer = ""
            return False
        self._previous = stripped
        return True

    def _release(self, text: str, final: bool) -> list[str]:
        output: list[str] = []
        sentences, rest = split_complete_sentences(text)
        for sentence, separator in sentences:
            if not self._approve(sentence):
                return output
            output.append(sentence + separator)
        if final:
            if rest:
                if not self._approve(rest):
                    return output
                output.append(rest)
            self._buffer = ""
            return output
        # No full stop in sight: release long stretches in bounded pieces so the user is not kept waiting.
        while len(rest) > self._max_buffer:
            cut = rest.rfind(" ", 0, self._max_buffer)
            cut = cut if cut > 0 else self._max_buffer
            piece, rest = rest[:cut], rest[cut:]
            lead = rest[:1] if rest[:1] == " " else ""
            rest = rest[len(lead):]
            if not self._approve(piece):
                return output
            output.append(piece + lead)
        self._buffer = rest
        return output
