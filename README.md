# Insight-Pilot

Literature research automation for AI agents. Searches arXiv and OpenAlex, deduplicates results, downloads PDFs, and generates research indexes.

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

# Run full pipeline (search → merge → dedup → download → index)
insight-pilot pipeline \
  --project ./research/webagent \
  --since 2025-07-01 \
  --limit 100
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize a research project |
| `search` | Search papers from arXiv or OpenAlex |
| `merge` | Merge search results |
| `dedup` | Deduplicate items |
| `download` | Download PDFs |
| `index` | Generate index.md |
| `status` | Show project status |
| `pipeline` | Run full workflow |

Use `--json` flag for structured output (recommended for AI agents).

## Repository Structure

```
insight-pilot/
├── pyproject.toml           # Package configuration
├── src/insight_pilot/       # Python package
│   ├── cli.py               # CLI entry point
│   ├── search/              # Search modules (arXiv, OpenAlex)
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

## License

MIT
