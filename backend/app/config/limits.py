"""Approved input limits (decision G5). Single source of truth for backend validation.

The frontend mirrors these values for its live counter; the backend is the authority.
"""

MAX_MESSAGE_CHARS = 500
MAX_HISTORY_MESSAGES = 20
# Counted as characters (not bytes): the current message plus the content of every history message.
MAX_TOTAL_CHARS = 8000
