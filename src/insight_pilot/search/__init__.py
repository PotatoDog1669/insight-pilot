"""Search modules for different sources."""
from insight_pilot.search.arxiv import search as search_arxiv
from insight_pilot.search.openalex import search as search_openalex

__all__ = ["search_arxiv", "search_openalex"]
