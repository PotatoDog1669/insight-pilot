import os

import pytest

from insight_pilot.search.github import search as search_github
from insight_pilot.search.openalex import search as search_openalex


pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION"),
    reason="Set RUN_INTEGRATION=1 to enable network integration tests",
)


def test_github_search_smoke():
    results = search_github("agent", limit=3, types=["repositories"], token=os.getenv("GITHUB_TOKEN"))
    assert isinstance(results, list)
    assert results


def test_openalex_search_smoke():
    results = search_openalex("agent", limit=3)
    assert isinstance(results, list)
    assert results
