"""Check the chunk file before anything is sent to Pinecone: only chunks from approved sources, each
on that source's own host and complete enough to cite, with unique ids."""
import json
from urllib.parse import urlsplit

from vitalnest_ingest.models import Chunk

# Each approved source may only link to its own host (docs/sources.md).
ALLOWED_SOURCE_HOSTS = {"MedlinePlus": {"medlineplus.gov"}, "WHO": {"www.who.int"}, "CDC": {"www.cdc.gov"}}
ALLOWED_SOURCES = set(ALLOWED_SOURCE_HOSTS)
ALLOWED_HOSTS = set().union(*ALLOWED_SOURCE_HOSTS.values())
REQUIRED_TEXT_FIELDS = ("text", "title", "attribution", "licence")
MAX_METADATA_BYTES = 30_000  # Pinecone allows 40 KB per vector; stay well below
MAX_PROBLEMS_SHOWN = 5


class ChunkValidationError(Exception):
    """The chunk file is not safe to upload. The message lists the first few problems."""


def _problems(chunks: list[Chunk]):
    seen: set[str] = set()
    for chunk in chunks:
        label = chunk.chunk_id or "<no id>"
        if chunk.chunk_id in seen:
            yield f"duplicate chunk id {label}"
        seen.add(chunk.chunk_id)
        if chunk.source_name not in ALLOWED_SOURCES:
            yield f"{label}: source {chunk.source_name!r} is not an approved source"
        else:
            parts = urlsplit(chunk.url)
            if parts.scheme != "https" or parts.hostname not in ALLOWED_SOURCE_HOSTS[chunk.source_name]:
                yield f"{label}: url is not https on an approved host"
        for field in REQUIRED_TEXT_FIELDS:
            if not str(getattr(chunk, field)).strip():
                yield f"{label}: {field} is empty"
        if len(json.dumps(chunk.metadata(), ensure_ascii=False).encode("utf-8")) > MAX_METADATA_BYTES:
            yield f"{label}: metadata is too large for Pinecone"


def validate_chunks(chunks: list[Chunk]) -> None:
    if not chunks:
        raise ChunkValidationError("The file contains no chunks")
    problems = list(_problems(chunks))
    if problems:
        shown = "; ".join(problems[:MAX_PROBLEMS_SHOWN])
        more = f" (and {len(problems) - MAX_PROBLEMS_SHOWN} more)" if len(problems) > MAX_PROBLEMS_SHOWN else ""
        raise ChunkValidationError(f"{len(problems)} problem(s) found, nothing was uploaded: {shown}{more}")
