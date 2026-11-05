"""Command line for the manual ingestion run (decision G2).

    python -m vitalnest_ingest fetch            download the newest MedlinePlus topics file
    python -m vitalnest_ingest fetch-who        download the listed WHO fact sheets (polite, cached)
    python -m vitalnest_ingest fetch-cdc        download the reviewed list of CDC pages (polite, cached)
    python -m vitalnest_ingest build            clean, chunk, write chunks.jsonl and the BM25 index
    python -m vitalnest_ingest upload           embed chunks and upsert them to Pinecone

Steps are separate so `build` works offline and only `upload` needs the Pinecone key.
"""
import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import httpx

from app.retrieval.pinecone_config import INDEX_NAME, NAMESPACE
from vitalnest_ingest import bm25_index, cdc, fetching, medlineplus, pages, vectors, who
from vitalnest_ingest.chunking import DEFAULT_MAX_CHARS, DEFAULT_OVERLAP_CHARS, chunk_document
from vitalnest_ingest.files import write_text_atomic
from vitalnest_ingest.models import Chunk
from vitalnest_ingest.validation import ChunkValidationError, validate_chunks

DATA_DIR = Path("data")
WHO_DIR = DATA_DIR / "raw" / "who"
CDC_DIR = DATA_DIR / "raw" / "cdc"
CDC_LIST = Path("cdc_pages.txt")


PROBE_PAUSE = 1.0  # seconds between date probes, to stay polite to the NLM server


def _fail(message: str) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return 1


def _fetch(args: argparse.Namespace) -> int:
    try:
        with fetching.make_client() as client:
            url = fetching.find_latest_topics_url(client, date.today(), pause=PROBE_PAUSE)
            destination = Path(args.output_dir) / url.rsplit("/", 1)[-1]
            fetching.download(client, url, destination, overwrite=args.force)
    except (httpx.HTTPError, LookupError, FileExistsError, ValueError, OSError) as error:
        return _fail(str(error) or type(error).__name__)
    print(f"Downloaded {url} -> {destination}")
    return 0


def _fetch_who(args: argparse.Namespace) -> int:
    slugs = args.only or who.all_slugs()
    saved = cached = 0
    failed: list[str] = []
    try:
        with pages.make_client() as client:
            fetcher = pages.FactSheetFetcher(client, Path(args.output_dir), delay=args.delay)
            for number, slug in enumerate(slugs, start=1):
                try:
                    _, downloaded = fetcher.fetch(slug, overwrite=args.force)
                except (pages.FetchRefused, httpx.HTTPStatusError, ValueError) as error:
                    failed.append(slug)
                    print(f"  skipped {slug}: {error}", file=sys.stderr)
                    continue
                saved, cached = saved + downloaded, cached + (not downloaded)
                if downloaded:
                    print(f"  {number}/{len(slugs)} {slug}", flush=True)
    except (httpx.HTTPError, OSError) as error:
        return _fail(str(error) or type(error).__name__)
    print(f"WHO fact sheets: {saved} downloaded, {cached} already saved, {len(failed)} skipped -> {args.output_dir}")
    return 0


def _fetch_cdc(args: argparse.Namespace) -> int:
    try:
        keys = args.only or cdc.load_page_list(Path(args.list))
    except (OSError, ValueError) as error:
        return _fail(str(error))
    saved = cached = 0
    failed: list[str] = []
    try:
        with pages.make_client() as client:
            fetcher = pages.CdcFetcher(client, Path(args.output_dir), delay=args.delay)
            for number, key in enumerate(keys, start=1):
                try:
                    _, downloaded = fetcher.fetch(key, overwrite=args.force)
                except (pages.FetchRefused, httpx.HTTPStatusError, ValueError) as error:
                    failed.append(key)
                    print(f"  skipped {key}: {error}", file=sys.stderr)
                    continue
                saved, cached = saved + downloaded, cached + (not downloaded)
                if downloaded:
                    print(f"  {number}/{len(keys)} {key}", flush=True)
    except (httpx.HTTPError, OSError) as error:
        return _fail(str(error) or type(error).__name__)
    print(f"CDC pages: {saved} downloaded, {cached} already saved, {len(failed)} skipped -> {args.output_dir}")
    return 0


def _build(args: argparse.Namespace) -> int:
    source = Path(args.input)
    out = Path(args.output_dir)
    outputs = [out / "chunks.jsonl", out / "bm25_index.json"]
    existing = [str(path) for path in outputs if path.exists()]
    if existing and not args.force:
        return _fail(f"{', '.join(existing)} already exists; pass --force to replace it")
    if not source.is_file():
        return _fail(f"Input file not found: {source}")

    try:
        documents = medlineplus.parse_topics(source.read_bytes(), retrieved_at=args.retrieved_at)
    except ValueError as error:
        return _fail(str(error))
    who_dir = Path(args.who_dir) if args.who_dir else source.parent / "who"  # next to the MedlinePlus file
    if who_dir.is_dir():
        who_documents, unusable = who.load_documents(who_dir, args.retrieved_at)
        documents.extend(who_documents)
        if unusable:
            print(f"Skipped {len(unusable)} unusable WHO page(s): {', '.join(unusable)}", file=sys.stderr)
    cdc_dir = Path(args.cdc_dir) if args.cdc_dir else source.parent / "cdc"
    if cdc_dir.is_dir():
        cdc_documents, skipped = cdc.load_documents(cdc_dir, args.retrieved_at)
        documents.extend(cdc_documents)
        for key, reason in skipped.items():
            print(f"Skipped CDC page {key}: {reason}", file=sys.stderr)
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(chunk_document(document, args.max_chars, args.overlap_chars))
    if not chunks:
        return _fail("The file contains no usable topics; nothing was written")

    try:
        lines = "".join(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n" for chunk in chunks)
        write_text_atomic(outputs[0], lines)
        bm25_index.save_index(chunks, outputs[1])
    except OSError as error:
        return _fail(f"Could not write output: {error}")
    by_source = ", ".join(f"{name} {sum(1 for d in documents if d.source_name == name)}" for name in sorted({d.source_name for d in documents}))
    print(f"{len(documents)} topics ({by_source}) -> {len(chunks)} chunks written to {out}")
    return 0


def _load_chunks(path: Path) -> list[Chunk]:
    if not path.is_file():
        raise FileNotFoundError(path)
    chunks: list[Chunk] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            chunks.append(Chunk(**json.loads(line)))
        except (ValueError, TypeError) as error:
            raise ChunkValidationError(f"Line {number} of {path} is not a valid chunk") from error
    return chunks


def _print_progress(done: int, total: int) -> None:
    print(f"  {done}/{total} chunks stored", flush=True)


def _upload(args: argparse.Namespace) -> int:
    api_key = os.environ.get("PINECONE_API_KEY")
    if not api_key and not args.dry_run:
        print("PINECONE_API_KEY is not set. Export it in your shell; never put it in a file.", file=sys.stderr)
        raise SystemExit(2)
    try:
        chunks = _load_chunks(Path(args.chunks))
        validate_chunks(chunks)
        if args.source:
            chunks = [chunk for chunk in chunks if chunk.source_name in args.source]
            if not chunks:
                return _fail(f"No chunks from {', '.join(args.source)} in {args.chunks}")
    except FileNotFoundError:
        return _fail(f"Chunk file not found: {args.chunks}")
    except ChunkValidationError as error:
        return _fail(str(error))

    if args.dry_run:
        sources = sorted({chunk.source_name for chunk in chunks})
        topics = len({chunk.doc_id for chunk in chunks})
        print(f"Dry run: {len(chunks)} chunks from {topics} topics, sources: {', '.join(sources)}.")
        print(f"Target: index '{args.index_name}', namespace {NAMESPACE or '(default)'!r}. No data was sent.")
        return 0

    try:
        embedder, store = vectors.open_pinecone(api_key, args.index_name)
        count = vectors.upsert_chunks(chunks, embedder, store, args.batch_size, progress=_print_progress)
    except (vectors.UploadTargetError, vectors.UploadError, ValueError) as error:
        return _fail(str(error))
    print(f"Upserted {count} chunks to index '{args.index_name}'")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vitalnest_ingest")
    commands = parser.add_subparsers(dest="command", required=True)

    fetch = commands.add_parser("fetch")
    fetch.add_argument("--output-dir", default=str(DATA_DIR / "raw"))
    fetch.add_argument("--force", action="store_true", help="replace an existing download")
    fetch.set_defaults(run=_fetch)

    fetch_cdc = commands.add_parser("fetch-cdc")
    fetch_cdc.add_argument("--list", default=str(CDC_LIST), help="reviewed list of CDC page paths")
    fetch_cdc.add_argument("--output-dir", default=str(CDC_DIR))
    fetch_cdc.add_argument("--only", nargs="+", help="fetch just these page paths")
    fetch_cdc.add_argument("--delay", type=float, default=pages.DEFAULT_DELAY, help="seconds between requests")
    fetch_cdc.add_argument("--force", action="store_true", help="download again even if already saved")
    fetch_cdc.set_defaults(run=_fetch_cdc)

    fetch_who = commands.add_parser("fetch-who")
    fetch_who.add_argument("--output-dir", default=str(WHO_DIR))
    fetch_who.add_argument("--only", nargs="+", help="fetch just these fact-sheet names")
    fetch_who.add_argument("--delay", type=float, default=pages.DEFAULT_DELAY, help="seconds between requests")
    fetch_who.add_argument("--force", action="store_true", help="download again even if already saved")
    fetch_who.set_defaults(run=_fetch_who)

    build = commands.add_parser("build")
    build.add_argument("--input", required=True)
    build.add_argument("--output-dir", default=str(DATA_DIR / "build"))
    build.add_argument("--retrieved-at", default=date.today().isoformat())
    build.add_argument("--cdc-dir", default=None, help="saved CDC pages (default: a 'cdc' folder next to --input), included if it exists")
    build.add_argument("--who-dir", default=None, help="saved WHO fact sheets (default: a 'who' folder next to --input), included if it exists")
    build.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    build.add_argument("--overlap-chars", type=int, default=DEFAULT_OVERLAP_CHARS)
    build.add_argument("--force", action="store_true", help="replace existing build outputs")
    build.set_defaults(run=_build)

    upload = commands.add_parser("upload")
    upload.add_argument("--chunks", default=str(DATA_DIR / "build" / "chunks.jsonl"))
    upload.add_argument("--index-name", default=INDEX_NAME)
    upload.add_argument("--source", nargs="+", help="send only chunks from these sources, e.g. WHO")
    upload.add_argument("--dry-run", action="store_true", help="validate the file and show the target; send nothing")
    upload.add_argument("--batch-size", type=int, default=vectors.DEFAULT_BATCH_SIZE)
    upload.set_defaults(run=_upload)

    args = parser.parse_args(argv)
    return args.run(args)
