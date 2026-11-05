"""Request schemas for the chat API. Pydantic enforces every limit before any work happens."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from app.config.limits import MAX_HISTORY_MESSAGES, MAX_MESSAGE_CHARS, MAX_TOTAL_CHARS

# Surrounding whitespace is removed first, so "   " counts as empty and padding never counts.
TrimmedText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

# Error type raised when the total size is exceeded; the API maps it to HTTP 413.
PAYLOAD_TOO_LARGE = "payload_too_large"


class StrictModel(BaseModel):
    # Unknown fields are an error: clients cannot smuggle extra data into the pipeline.
    model_config = ConfigDict(extra="forbid")


class HistoryMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: TrimmedText


class ChatRequest(StrictModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)]
    # Too many messages is rejected, never silently truncated (decision D2).
    history: list[HistoryMessage] = Field(default_factory=list, max_length=MAX_HISTORY_MESSAGES)

    @model_validator(mode="after")
    def check_total_size(self) -> "ChatRequest":
        total = len(self.message) + sum(len(item.content) for item in self.history)
        if total > MAX_TOTAL_CHARS:
            raise PydanticCustomError(
                PAYLOAD_TOO_LARGE,
                "Total request size must be at most {limit} characters",
                {"limit": MAX_TOTAL_CHARS},
            )
        return self
