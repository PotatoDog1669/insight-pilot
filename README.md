# Insight-Pilot

Literature research automation for AI agents. Searches papers, code, and blogs, deduplicates results, downloads PDFs, and generates research indexes.

## Installation

### For Users / AI Agents

```bash
# Install directly from GitHub
pip install git+https://github.com/PotatoDog1669/insight-pilot.git

# Or with uv
uv pip install git+https://github.com/PotatoDog1669/insight-pilot.git
```

### For Development

```bash
git clone https://github.com/PotatoDog1669/insight-pilot.git
cd insight-pilot
pip install -e .
```

## Quick Start

```bash
# Initialize a research project
insight-pilot init \
  --topic "Web Agents" \
  --keywords "web agent,browser automation,gui agent" \
  --output ./research/webagent

# Search (multiple sources supported)
insight-pilot search \
  --project ./research/webagent \
  --source arxiv openalex \
  --query "web agent" \
  --since 2025-07-01 \
  --limit 100

# Download PDFs + convert to Markdown
insight-pilot download --project ./research/webagent

# Generate index
insight-pilot index --project ./research/webagent
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize a research project |
| `search` | Search sources (arXiv, OpenAlex, GitHub, PubMed, Dev.to, blogs) |
| `download` | Download PDFs + convert to Markdown |
| `analyze` | Analyze papers with LLM |
| `index` | Generate index.md |
| `status` | Show project status |
| `sources` | Manage blog/RSS sources |

Use `--json` flag for structured output (recommended for AI agents).

## Repository Structure

```
insight-pilot/
├── pyproject.toml           # Package configuration
├── src/insight_pilot/       # Python package
│   ├── cli.py               # CLI entry point
│   ├── search/              # Search modules (papers, GitHub, blogs)
│   ├── process/             # Merge & dedup
│   ├── download/            # PDF download
│   └── output/              # Index generation
├── .codex/skills/insight-pilot/  # Skill documentation (for AI agents)
│   └── SKILL.md                  # Agent-friendly documentation
└── research/                # Research projects (gitignored)
```

## For AI Agents

See [.codex/skills/insight-pilot/SKILL.md](.codex/skills/insight-pilot/SKILL.md) for detailed agent-friendly documentation including:
- Command reference with all arguments
- JSON output format
- Error codes and retry guidance
- Python API for advanced use

## Sources Configuration (Blog/RSS)

Create `sources.yaml` in your project root:

```yaml
blogs:
  - name: "Cursor Blog"
    type: "ghost"
    url: "https://cursor.sh/blog"
    api_key: "auto"
  - name: "Example WP Blog"
    type: "wordpress"
    url: "https://blog.example.com"
  - name: "OpenAI Blog"
    type: "rss"
    url: "https://openai.com/blog/rss.xml"
    category: "ai"
```

Manage sources via:

```bash
insight-pilot sources --project ./research/webagent
```

Environment variables:
- `GITHUB_TOKEN` (GitHub rate limit bump)
- `PUBMED_EMAIL` (required by NCBI)
- `OPENALEX_MAILTO` (OpenAlex polite usage)
- `INSIGHT_PILOT_SOURCES` (override `sources.yaml` path)

See `sources.yaml.example` for a curated starter list.

## License

MIT
