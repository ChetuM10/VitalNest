"""Greetings, thanks and goodbyes: a friendly fixed reply, with no search and no Claude call.

Only a message that is nothing but small talk counts ("hi" yes, "hey, what are asthma symptoms?" no),
so a real question is never swallowed. Case, punctuation, emoji, apostrophes and stretched letters
("heyyy", "byeee") do not matter. The safety check runs before this, so "hi, I can't breathe" is an emergency.
"""
import re
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
_GREETING = re.compile(rf"(?:{_OPENER}|{_CASUAL}|{_HOW}){_ADDRESS}(?: (?:{_CASUAL}|{_HOW}))?(?: {_HOW})?")

_HELP = re.compile(r"(?:help|what can you do|who are you|what are you|what do you do)(?: vitalnest)?")

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


def detect_small_talk(message: str) -> SmallTalk | None:
    text = _normalise(message)
    if not text:
        return None
    if _GOODBYE.fullmatch(text):
        return SmallTalk(messages.GOODBYE_MESSAGE)
    if _THANKS_RE.fullmatch(text):
        return SmallTalk(messages.THANKS_MESSAGE)
    if _GREETING.fullmatch(text) or _HELP.fullmatch(text):
        return SmallTalk(messages.GREETING_MESSAGE)
    return None
