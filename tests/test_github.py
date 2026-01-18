from insight_pilot.search.github import extract_paper_links, transform_repo_item


def test_extract_paper_links():
    readme = "See https://arxiv.org/abs/1234.5678 and DOI 10.5555/abcd.123."
    links = extract_paper_links(readme)
    assert "https://arxiv.org/abs/1234.5678" in links
    assert "https://doi.org/10.5555/abcd.123" in links


def test_transform_repo_item():
    repo = {
        "id": 42,
        "full_name": "acme/rocket",
        "description": "Rocket science",
        "owner": {"login": "acme"},
        "stargazers_count": 10,
        "forks_count": 2,
        "topics": ["ai", "agents"],
        "html_url": "https://github.com/acme/rocket",
    }
    item = transform_repo_item(repo, "README", {"sha": "abc"}, ["alice"])
    assert item["type"] == "github"
    assert item["title"] == "acme/rocket"
    assert item["metadata"]["stars"] == 10
