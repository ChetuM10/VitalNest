"""Tokenizer shared by the ingestion script (BM25 index build) and the API (query time).

Both sides must tokenize identically or BM25 silently stops matching, so there is exactly one
implementation. Changing it requires rebuilding the index.
"""
import re

_TOKEN = re.compile(r"\w+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.casefold())
