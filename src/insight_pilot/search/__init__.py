"""Search modules for different sources."""
from insight_pilot.search.arxiv import search as search_arxiv
from insight_pilot.search.openalex import search as search_openalex
from insight_pilot.search.github import search as search_github
from insight_pilot.search.pubmed import search as search_pubmed
from insight_pilot.search.devto import search as search_devto
from insight_pilot.search.blog import search as search_blog
from insight_pilot.search.rss import search as search_rss

__all__ = [
    "search_arxiv",
    "search_openalex",
    "search_github",
    "search_pubmed",
    "search_devto",
    "search_blog",
    "search_rss",
]
