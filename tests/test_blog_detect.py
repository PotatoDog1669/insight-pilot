from insight_pilot.search.blog import detect_platform_from_html, discover_ghost_api_key, discover_rss_url


def test_detect_platform_from_html():
    ghost_html = '<script>var config={"contentApiKey":"abc123abc123abc123abc123"};</script>'
    wp_html = '<meta name="generator" content="WordPress 6.0" />'
    assert detect_platform_from_html(ghost_html) == "ghost"
    assert detect_platform_from_html(wp_html) == "wordpress"


def test_discover_ghost_api_key():
    html = '<meta name="ghost:content-api-key" content="deadbeefdeadbeefdeadbeef" />'
    assert discover_ghost_api_key(html) == "deadbeefdeadbeefdeadbeef"


def test_discover_rss_url():
    html = '<link rel="alternate" type="application/rss+xml" href="/feed.xml" />'
    rss_url = discover_rss_url(html, "https://example.com/blog")
    assert rss_url == "https://example.com/feed.xml"
