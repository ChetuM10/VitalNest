"""Pinecone settings shared by ingestion (which writes) and the API (which reads).

They live in one place so the two sides cannot drift apart: a different model, metric or
namespace on one side would make every search quietly return nothing useful.
"""
INDEX_NAME = "vitalnest"
EMBEDDING_MODEL = "multilingual-e5-large"
EMBEDDING_DIMENSION = 1024
METRIC = "cosine"
# Pinecone's default namespace. Named here so uploads and queries always use the same one.
NAMESPACE = ""
