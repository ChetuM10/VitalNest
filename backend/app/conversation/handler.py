"""Conversation handling: tidy the history the client sent and build a standalone search query.

The query rewrite is a simple rule, not an LLM call (no extra cost or latency). It handles common
follow-ups such as "How is it treated?" and will miss subtler ones; an LLM rewrite is an optional
upgrade (see the plan).
"""
import re

from app.api.schemas import HistoryMessage

MAX_ANCHOR_CHARS = 300

_FOLLOW_UP_START = re.compile(
    r"^\W*(?:and|also|but|so|then|what about|how about|why|what else|any other|anything else|more)\b"
)
_PRONOUNS = {"it", "its", "they", "them", "their", "he", "she", "those", "these"}
_DEMONSTRATIVES = {"this", "that"}  # only counted near the start: "that" is often just a connecting word
_EARLY_TOKENS = 5


def normalise_history(history: list[HistoryMessage]) -> list[HistoryMessage]:
    """Make the history a clean user/assistant alternation that starts with a user turn.

    Leading assistant messages are dropped, consecutive messages from one role are merged, and a
    trailing user message with no answer is dropped (the new question follows it).
    """
    merged: list[HistoryMessage] = []
    for message in history:
        if not merged and message.role == "assistant":
            continue
        if merged and merged[-1].role == message.role:
            merged[-1] = HistoryMessage(role=message.role, content=f"{merged[-1].content}\n\n{message.content}")
        else:
            merged.append(message)
    if merged and merged[-1].role == "user":
        merged.pop()
    return merged


def recent_history(history: list[HistoryMessage], max_messages: int = 6) -> list[HistoryMessage]:
    """Keep only the latest messages (cost control), still starting with a user turn."""
    tail = history[-max_messages:]
    while tail and tail[0].role == "assistant":
        tail = tail[1:]
    return tail


def is_follow_up(message: str) -> bool:
    text = message.casefold()
    if _FOLLOW_UP_START.match(text):
        return True
    tokens = re.findall(r"\w+", text)
    return any(token in _PRONOUNS for token in tokens) or any(
        token in _DEMONSTRATIVES for token in tokens[:_EARLY_TOKENS]
    )


def standalone_query(message: str, history: list[HistoryMessage]) -> str:
    """The text to search with: the message itself, plus the topic question it refers back to."""
    cleaned = normalise_history(history)
    if not cleaned or not is_follow_up(message):
        return message
    user_questions = [m.content for m in cleaned if m.role == "user"]
    if not user_questions:
        return message
    # Use the most recent question that stands on its own, so chains of follow-ups keep the topic.
    anchor = next((q for q in reversed(user_questions) if not is_follow_up(q)), user_questions[-1])
    if len(anchor) > MAX_ANCHOR_CHARS:
        anchor = anchor[:MAX_ANCHOR_CHARS].rsplit(" ", 1)[0]
    return f"{anchor} {message}"
