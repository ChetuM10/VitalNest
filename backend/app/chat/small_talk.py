"""Greetings, small talk, openers ("I need help"), thanks and goodbyes: a friendly reply, with no search and no
Claude call. Each kind has a few reply variants and one is picked at random.

Only a message that is nothing but small talk counts ("hi" yes, "hey, what are asthma symptoms?" no),
so a real question is never swallowed. Case, punctuation, emoji, apostrophes and stretched letters
("heyyy", "byeee") do not matter. The safety check runs before this, so "hi, I can't breathe" is an emergency.
"""
import random
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.safety import messages


@dataclass(frozen=True)
class SmallTalk:
    reply: str


_OPENER = r"(?:hi+|hello+|hey+|hiya|howdy|greetings|yo+|good (?:morning|afternoon|evening|day)|morning|afternoon|evening)"
_CASUAL = r"(?:sup|wassup|wazzup|whatsup|whats up|what is up|what up)"
_HOW = (
    r"(?:how are you(?: doing)?(?: today)?|how r u|how are u|hru|hows it going|how is it going|"
    r"hows everything|how do you do|hows life)"
)
_ADDRESS = r"(?: (?:there|everyone|all|friend|buddy|vitalnest))?"
_PREFIX = rf"(?:{_OPENER}{_ADDRESS} )?"
_GREETING = re.compile(rf"{_OPENER}{_ADDRESS}")
_HOW_ARE_YOU = re.compile(rf"{_PREFIX}{_HOW}{_ADDRESS}(?: {_CASUAL})?|{_PREFIX}{_CASUAL}{_ADDRESS} {_HOW}")
_CASUAL_TALK = re.compile(rf"{_PREFIX}{_CASUAL}{_ADDRESS}")

_INTRO = re.compile(r"(?:what can you do|who are you|what are you|what do you do)(?: vitalnest)?")

# "I need help", "can you help me?", "I have a question": the person is opening a conversation, not asking one yet.
# A message that says what the help is for ("can you help me with my headache") is not matched: it is a real question.
_OPENER_TALK = re.compile(
    r"(?:(?:ok|okay|hey|hi|hello|please) )?(?:"
    r"help(?: me| please| me please)?|"
    r"(?:i )?(?:need|want|could use|would like) (?:some |your |a little |a bit of )?(?:help|assistance|advice)(?: please)?|"
    r"(?:can|could|would|will) you (?:please )?help(?: me| us)?(?: out)?(?: please)?|"
    r"(?:i )?(?:have|got|ive got|ive) (?:a |an |one |another |some |a few )?(?:quick |small |little |health |medical |general )?questions?(?: for you)?|"
    r"(?:i )?(?:want|would like|id like) to ask (?:you )?(?:a |an |one |some )?(?:quick |small |little |health )?(?:question|something)s?|"
    r"(?:can|may|could) i ask (?:you )?(?:a |an |one |some )?(?:quick |small |little |health )?(?:question|something)s?(?: please)?|"
    r"(?:quick |small |one )?questions?|"
    r"i(?: am|m) (?:here|looking) for (?:some )?(?:help|information|info|advice)"
    r")(?: vitalnest)?"
)

_THANK_WORD = (
    r"(?:thanks+|thanx+|thankyou+|thank you+|thank u|thx|ty|cheers|many thanks|much appreciated|"
    r"(?:i )?(?:really |truly |do )?appreciate (?:it|that|this|your help))"
)
_THANKS = (
    r"(?:(?:ok|okay|great|perfect|awesome|cool|nice|wonderful|brilliant|lovely) )?"
    rf"{_THANK_WORD}(?: (?:so|very))?(?: (?:much|a lot|a ton|a bunch))?(?: vitalnest)?(?: again)?"
    r"(?: for (?:the |your )?(?:help|answer|info|information|reply|response|that))?"
)
_THANKS_RE = re.compile(_THANKS)

_BYE_WORD = (
    r"(?:bye+(?: bye+)?|goodbye+|good bye|see you(?: (?:soon|later|around|tomorrow|next time))?|see ya(?: later| soon)?|cya|"
    r"catch you later|catch ya later|talk to you later|talk later|ttyl|later|farewell|good night|goodnight|take care|so long|"
    r"have a (?:good|great|nice|lovely) (?:day|night|one|evening|weekend)|im off|i am off)"
)
_GOODBYE = re.compile(rf"(?:(?:ok|okay|alright|well|great|cool|right) )?(?:{_THANKS} )?{_BYE_WORD}(?: (?:vitalnest|everyone|all|now|then|for now))?")


def _normalise(text: str) -> str:
    text = text.casefold().replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z ]", " ", text)  # punctuation, digits and emoji become spaces
    text = re.sub(r"(.)\1{2,}", r"\1", text)  # "heyyy" -> "hey", "byeee" -> "bye"
    return re.sub(r"\s+", " ", text).strip()


# Checked in this order; the first full match decides the kind of reply.
_KINDS: tuple[tuple[re.Pattern, Sequence[str]], ...] = (
    (_GOODBYE, messages.GOODBYE_REPLIES),
    (_THANKS_RE, messages.THANKS_REPLIES),
    (_HOW_ARE_YOU, messages.HOW_ARE_YOU_REPLIES),
    (_CASUAL_TALK, messages.CASUAL_REPLIES),
    (_OPENER_TALK, messages.OPENER_REPLIES),
    (_INTRO, (messages.GREETING_MESSAGE,)),
    (_GREETING, messages.GREETING_REPLIES),
)


def detect_small_talk(message: str, choose: Callable[[Sequence[str]], str] = random.choice) -> SmallTalk | None:
    """The reply for a message that is only small talk, else None. `choose` picks the variant (tests pass their own)."""
    text = _normalise(message)
    if not text:
        return None
    for pattern, replies in _KINDS:
        if pattern.fullmatch(text):
            return SmallTalk(choose(replies))
    return None
