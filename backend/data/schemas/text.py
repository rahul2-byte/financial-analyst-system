from pydantic import BaseModel
from datetime import datetime
from typing import List, Dict, Optional


class NewsArticle(BaseModel):
    ticker: str
    title: str
    url: str
    source: str
    published_date: datetime
    summary: Optional[str] = None
    content: str


class ProcessedChunk(BaseModel):
    chunk_id: str
    ticker: str
    text: str
    metadata: Dict[str, str]  # source, date, url
    embedding: Optional[List[float]] = None
