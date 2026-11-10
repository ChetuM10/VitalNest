"""Ask a short follow-up when someone says they are unwell but not what is wrong, before any search.

"I am not feeling well" is not a question the sources can answer, so it used to fall through to the
generic no-context reply. Here it gets a fixed, friendly question instead (no search, no Claude call).

Two steps, one question at a time, never repeated:
  1. a vague statement ("I'm not feeling well", "something is wrong")      -> ask what they are experiencing;
  2. a symptom with no length of time ("I've been having headaches")      -> ask how long, and about other symptoms.
Once the person has given enough ("I've had a headache since yesterday and I feel dizzy"), or two questions have
already been asked, nothing is asked and the normal pipeline runs. The earlier answers are folded into the
search text, so "since yesterday" is searched together with "headaches".

Safety runs before this (service.py), so an emergency or self-harm message is never held up by a question.
The conversation memory is the `history` the client already sends: a clarification is recognised by its exact text.
"""
import random
import re
from collections.abc import Callable, Sequence

from app.api.schemas import HistoryMessage
from app.chat.small_talk import _normalise
from app.conversation.handler import normalise_history

# ---- fixed replies (the first of each is the wording the owner specified) ----
ASK_WHAT_REPLIES = (
    "I'm sorry you're not feeling well. Help me understand exactly what's going on. What are you experiencing right now?",
    "I'm sorry to hear that. What symptoms or changes have you noticed?",
)
ASK_HOW_LONG_REPLIES = (
    "How long have you been experiencing this? Have you noticed any other symptoms?",
    "How long has this been going on? Have you noticed anything else along with it?",
)
ASK_MORE_REPLIES = (
    "Could you tell me a little more? For example, is it pain, a fever, tiredness, or something else?",
)
_ALL_REPLIES = frozenset(ASK_WHAT_REPLIES + ASK_HOW_LONG_REPLIES + ASK_MORE_REPLIES)
_HOW_LONG = frozenset(ASK_HOW_LONG_REPLIES)
MAX_QUESTIONS = 2  # in a row; after that the normal pipeline runs

# ---- vague statements (matched against the whole normalised message) ----
_LEAD_IN = r"(?:(?:ok|okay|hey|hi|hello|well|um|so|sorry|honestly|actually) )?"
_INTENSIFIER = r"(?:(?:really|very|so|quite|kind of|kinda|a bit|a little|just|pretty|too|that|feeling|been|feel) )*"
_BAD_STATE = (
    r"(?:not (?:feeling )?(?:very |so |too |that |really |quite )?(?:well|good|okay|ok|great|right|myself|fine)|"
    r"unwell|sick|ill|poorly|terrible|awful|bad|horrible|crappy|off|under the weather|lousy|rough|not myself|not like myself)"
)
_GOOD_WORD = r"(?:well|good|okay|ok|great|right|myself|fine|like myself)"
_SUBJECT = r"(?:i am|im|i feel|ive been|i have been|i been|i am feeling|im feeling|ive been feeling|i have been feeling|feeling|been feeling|)"
_NEGATED = r"(?:i dont feel|i do not feel|i havent been feeling|i have not been feeling|ive not been feeling|i dont really feel|i am not feeling|im not feeling|not feeling|i havent felt|i have not felt)"
_TAIL = (
    r"(?: (?:today|right now|lately|these days|at the moment|since morning|a lot|again|for a while))*"
    r"(?: (?:please|can you help me|can you help|could you help me|help me|what should i do|what do i do|any advice|any suggestions))?"
)
_VAGUE_FORMS = (
    rf"{_SUBJECT} ?{_INTENSIFIER}{_BAD_STATE}",
    rf"{_NEGATED} {_INTENSIFIER}{_GOOD_WORD}",
    r"something (?:is|feels|seems) (?:wrong|off|not right)(?: with me| in my body| with my body)?",
    r"(?:i )?(?:think )?(?:i am|im) (?:sick|ill|unwell)",
    r"(?:i )?(?:need|want) (?:some |your )?(?:help|advice|support) with my health",
    r"(?:i )?(?:need|want) (?:some )?(?:medical|health) (?:help|advice)",
    r"(?:i )?(?:have|got) (?:a |an )?(?:health|medical|physical) (?:problem|issue|concern|condition|worry)",
    r"(?:i am|im) (?:worried|concerned|anxious|scared) about my (?:health|body)",
    r"my health is (?:not |bad|poor|getting worse|declining)(?:good|well|great|okay|ok)?",
    r"(?:i am|im) (?:in pain|hurting|suffering|struggling)",
    r"(?:i am|im) (?:not|no) (?:ok|okay|alright|well)",
)
_VAGUE = re.compile(rf"{_LEAD_IN}(?:{'|'.join(_VAGUE_FORMS)}){_TAIL}")

# ---- a symptom statement that gives no length of time ----
_SYMPTOMS = re.compile(
    r"\b(?:headaches?|migraines?|dizz(?:y|iness)|light ?headed|nause(?:a|ous|ated)|vomit(?:ing)?|throwing up|fever(?:ish)?|temperature|chills?|"
    r"cough(?:ing)?|cold|flu|sore throat|runny nose|stuffy|congest(?:ed|ion)|sneezing|stomach ?ache|stomach pains?|belly pains?|tummy|cramps?|"
    r"diarrh?oea|constipat(?:ed|ion)|bloat(?:ed|ing)|heartburn|tired(?! of)|tiredness|fatigue|exhausted|weak(?:ness)?|rash|itch(?:y|ing)|"
    r"pains?|aching|aches?|hurts?|hurting|sore|swollen|swelling|insomnia|trouble sleeping|cant sleep|sweating|shaking|palpitations?|blurr?y vision|"
    r"earache|toothache|anxious|anxiety|stressed|depressed|sad)\b"
)
_FIRST_PERSON = re.compile(r"\b(?:i|im|ive|my|me)\b")
_ASKING = re.compile(r"\b(?:what|how|why|when|which|who|should|could|can|would|tell|explain|give|show|list)\b|^(?:is|are|do|does|did)\b")
_DURATION = re.compile(
    r"\b(?:since|ago|yesterday|today|tonight|morning|last night|all day|all week|all night|for (?:a |an |the |about |almost |over |around |the last |the past )?"
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|few|couple|several|while|long|day|days|week|weeks|month|months|year|years|hour|hours|minute|minutes)|"
    r"(?:\d+|few|couple|several) (?:of )?(?:days|weeks|months|years|hours|minutes)|days?|weeks?|months?|hours?|minutes?)\b"
)


def is_vague_unwell(message: str) -> bool:
    return bool(_VAGUE.fullmatch(_normalise(message)))


def is_symptom_without_duration(message: str, raw: str | None = None) -> bool:
    """A first-person symptom statement, not a question, that says nothing about how long."""
    if "?" in (raw if raw is not None else message):
        return False
    text = _normalise(message)
    return bool(
        _SYMPTOMS.search(text)
        and _FIRST_PERSON.search(text)
        and not _ASKING.search(text)
        and not _DURATION.search(text)
    )


def _chain(history: Sequence[HistoryMessage]) -> list[tuple[str, str]]:
    """The clarification questions asked at the end of the conversation, with the user message each followed.

    Returns [(question, user_message_before_it), ...], oldest first. Stops at the first reply that is not one of ours.
    """
    turns = normalise_history(list(history))
    chain: list[tuple[str, str]] = []
    index = len(turns) - 1
    while index >= 1 and turns[index].role == "assistant" and turns[index].content in _ALL_REPLIES:
        chain.append((turns[index].content, turns[index - 1].content))
        index -= 2
    chain.reverse()
    return chain


def clarifying_question(
    message: str, history: Sequence[HistoryMessage], choose: Callable[[Sequence[str]], str] = random.choice
) -> str | None:
    """The question to ask instead of searching, or None to carry on with the normal pipeline."""
    chain = _chain(history)
    if len(chain) >= MAX_QUESTIONS:
        return None
    if is_vague_unwell(message):
        return choose(ASK_WHAT_REPLIES if not chain else ASK_MORE_REPLIES)
    asked_how_long = any(question in _HOW_LONG for question, _ in chain)
    if not asked_how_long and is_symptom_without_duration(message):
        return choose(ASK_HOW_LONG_REPLIES)
    return None


def context_prefix(history: Sequence[HistoryMessage]) -> str:
    """After a clarification, what the person already said about their symptoms (vague openers left out).

    Search text is this plus the current message, so "since yesterday" is searched together with "headaches".
    Empty when the last assistant turn was not a clarification.
    """
    parts = [user for _, user in _chain(history) if not is_vague_unwell(user)]
    return " ".join(parts)
