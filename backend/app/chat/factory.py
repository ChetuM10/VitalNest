"""Build the chat service at startup from the keys in the environment.

Locally the keys come from ingestion/.env (see app/config/env.py); on AWS they will come from
Secrets Manager (T13). Without both keys no service is built: /v1/chat answers 503 and the rest
of the API (for example /v1/health) keeps working. Keys are never logged.
"""
import logging
import os

from app.chat.service import ChatService
from app.config.settings import no_context_min_dense_score
from app.llm.claude import ClaudeClient
from app.retrieval.dense import open_dense_retriever
from app.retrieval.pinecone_config import INDEX_NAME
from app.retrieval.spelling import SpellingCorrector

logger = logging.getLogger("vitalnest")


def build_chat_service(bm25) -> ChatService | None:
    pinecone_key = os.environ.get("PINECONE_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not pinecone_key or not anthropic_key:
        logger.warning("Chat is not configured: both PINECONE_API_KEY and ANTHROPIC_API_KEY must be set")
        return None
    dense = open_dense_retriever(pinecone_key, INDEX_NAME)
    claude = ClaudeClient.from_settings(anthropic_key)
    # Spelling help needs the page vocabulary, which comes from the keyword index; without it there is no correction.
    corrector = (
        SpellingCorrector(bm25.texts(), priority_texts=bm25.titles(), min_frequency=2) if bm25 is not None else None
    )
    return ChatService(dense, bm25, claude, min_dense_score=no_context_min_dense_score(), corrector=corrector)
