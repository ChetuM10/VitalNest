"""Shared constants for the shape of the model's reply: the answer, then the suggestions section."""

# The model writes this on its own line after the answer, followed by JSON with follow-up questions.
SUGGESTIONS_MARKER = "[[SUGGESTED_QUESTIONS]]"
