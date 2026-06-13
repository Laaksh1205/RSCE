from pydantic import BaseModel

class Paper(BaseModel):
    pmid: str
    title: str
    authors: list[str]
    year: int
    journal: str
    abstract_text: str
    full_text: str | None = None
    doi: str | None = None
