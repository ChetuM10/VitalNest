from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Document:
    """One source page/topic after cleaning, before chunking."""
    doc_id: str
    source_name: str
    title: str
    url: str
    text: str
    retrieved_at: str
    licence: str
    attribution: str


@dataclass(frozen=True)
class Chunk:
    """A retrievable piece of a document. Carries everything needed to cite it."""
    chunk_id: str
    doc_id: str
    source_name: str
    title: str
    url: str
    text: str
    retrieved_at: str
    licence: str
    attribution: str

    @property
    def embedding_text(self) -> str:
        """Text sent to the embedding model: the title gives each chunk its topic."""
        return f"{self.title}\n{self.text}"

    def to_dict(self) -> dict:
        return asdict(self)

    def metadata(self) -> dict:
        """Vector-store metadata: everything except the id, which is the vector id."""
        data = asdict(self)
        del data["chunk_id"]
        return data
