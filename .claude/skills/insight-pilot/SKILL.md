---
name: insight-pilot
description: Literature research automation - search arXiv/OpenAlex, deduplicate, download PDFs, analyze and generate research reports. Supports incremental updates.
version: 0.3.0
---

# Insight-Pilot Skill

A workflow automation skill for literature research. Searches arXiv and OpenAlex, deduplicates results, downloads PDFs, analyzes content, and generates incremental research reports.

## Setup (One-Time)

Create a virtual environment and install the package:

```bash
# Create venv for insight-pilot
python3 -m venv ~/.insight-pilot-venv

# Activate and install
source ~/.insight-pilot-venv/bin/activate
pip install git+https://github.com/PotatoDog1669/insight-pilot.git
```

If the GitHub package is not available, install from local repository:

```bash
source ~/.insight-pilot-venv/bin/activate
pip install -e /path/to/insight-pilot  # Replace with actual repo path
```

## Usage

Before running commands, activate the environment:

```bash
source ~/.insight-pilot-venv/bin/activate
```

Then use the CLI:

```bash
insight-pilot <command> [options]
```

## CLI Commands

| Command | Purpose | Required Args | Key Optional Args |
|---------|---------|---------------|-------------------|
| `init` | Create research project | `--topic`, `--output` | `--keywords` |
| `search` | Search single source | `--project`, `--source`, `--query` | `--limit`, `--since`, `--until` |
| `merge` | Combine raw results | `--project` | - |
| `dedup` | Remove duplicates | `--project` | `--dry-run`, `--similarity` |
| `download` | Fetch PDFs | `--project` | - |
| `convert` | Convert PDFs to Markdown | `--project` | `--force`, `--no-images` |
| `analyze` | Analyze papers with LLM | `--project` | `--config`, `--force` |
| `index` | Generate index.md | `--project` | `--template` |
| `status` | Check project state | `--project` | - |

### JSON Output Mode

Add `--json` flag for structured output (recommended for agents):

```bash
insight-pilot status --json --project ./research/myproject
```

---

## Workflow (Agent + CLI 协作)

这是一个 **Agent 与 CLI 协作**的完整工作流程。

**执行原则**：
- 🤖 **AUTO**: 自动执行，无需用户确认
- ⚠️ **AGENT TASK**: 需要 Agent 介入处理
- 所有 CLI 命令都是 AUTO，直接执行即可

### Phase 1: 搜索与初步筛选 🤖 AUTO

直接执行以下命令，无需确认：

```bash
PROJECT=./research/webagent

# Step 1: 初始化项目
insight-pilot init --topic "WebAgent Research" --keywords "web agent,browser agent" --output $PROJECT

# Step 2: 搜索多个数据源
insight-pilot search --project $PROJECT --source arxiv --query "web agent" --limit 50
insight-pilot search --project $PROJECT --source openalex --query "web agent" --limit 50

# Step 3: 合并搜索结果
insight-pilot merge --project $PROJECT

# Step 4: 自动去重（基于 DOI/arXiv ID/标题相似度）
insight-pilot dedup --project $PROJECT
```

### Phase 2: Agent 审核筛选 ⚠️ AGENT TASK

去重后，Agent 需要审核论文列表，去掉与研究主题无关的内容。

```bash
# 查看当前状态
insight-pilot status --json --project $PROJECT
```

**Agent 操作**：
1. 读取 `$PROJECT/.insight/items.json`
2. 逐条检查每篇论文的 `title` 和 `abstract`
3. 标记不相关的论文：将 `status` 设为 `"excluded"`，并添加 `exclude_reason`
4. 保存更新后的 `items.json`

```json
{
  "id": "i0023",
  "title": "Unrelated Paper Title",
  "status": "excluded",
  "exclude_reason": "Not related to web agents, focuses on chemical agents"
}
```

### Phase 3: 下载 PDF 🤖 AUTO

直接执行，无需确认：

```bash
# Step 5: 下载 PDF（只下载 status != "excluded" 的论文）
insight-pilot download --project $PROJECT
```

**下载结果**：
- 成功：`download_status: "success"`，PDF 保存到 `papers/`
- 失败：`download_status: "failed"`，记录到 `$PROJECT/.insight/download_failed.json`

失败列表格式：
```json
[
  {
    "id": "i0015",
    "title": "Paper Title",
    "url": "https://...",
    "error": "Connection timeout",
    "failed_at": "2026-01-17T10:30:00Z"
  }
]
```

> **Note**: 高级下载（使用代理/浏览器自动化处理失败项）功能尚未实现，后续版本支持。

### Phase 4: 转换与分析论文

**前置条件**：必须先完成 Phase 3 下载 PDF。

#### Step 6: PDF 转 Markdown 🤖 AUTO（可选但推荐）

将 PDF 转换为结构化 Markdown，保留表格、公式、图片等格式。支持两种后端：

| 后端 | 速度 | 质量 | 适用场景 |
|------|------|------|---------|
| `pymupdf4llm` | ⚡ 快 | 良好 | 大多数论文（默认） |
| `marker` | 🐢 慢 | 更好 | 复杂表格/公式 |

```bash
# 默认使用 pymupdf4llm（快速，推荐）
insight-pilot convert --project $PROJECT

# 使用 marker（更高质量但更慢）
pip install 'insight-pilot[marker]'  # 需要额外安装
insight-pilot convert --project $PROJECT --backend marker
```

**配置后端**：也可以在项目的 `config.yaml` 中配置默认后端：

```yaml
# $PROJECT/.insight/config.yaml
topic: "WebAgent Research"
keywords: [web agent, browser agent]

# PDF 转换配置
pdf_converter:
  backend: pymupdf4llm  # 或 "marker"
  page_chunks: false     # pymupdf4llm 选项
  use_llm: false         # marker 选项（需 API key）
```

**转换结果**：
- Markdown 文件保存到 `$PROJECT/.insight/markdown/{id}/{id}.md`
- 图片提取到 `$PROJECT/.insight/markdown/{id}/images/`（仅 marker）
- 元数据保存到 `$PROJECT/.insight/markdown/{id}/metadata.json`

#### Step 7: 分析论文

有两种方式：

##### 方式 A: LLM 自动分析 🤖 AUTO（推荐）

如果配置了 LLM，直接执行：

```bash
# 用 LLM 分析论文（优先使用已转换的 Markdown，否则回退到 PDF 文本提取）
insight-pilot analyze --project $PROJECT
```

**内容来源优先级**：
1. **Markdown** (from `convert`): 高质量结构化文本，保留表格、公式
2. **PDF 提取** (PyMuPDF): 基础文本提取，可能丢失格式

**LLM 配置**：创建 `.codex/skills/insight-pilot/llm.yaml`：

```yaml
provider: openai  # openai / anthropic / ollama
model: gpt-4o-mini
api_key: sk-xxx   # 或设置环境变量 OPENAI_API_KEY
```

##### 方式 B: Agent 手动分析 ⚠️ AGENT TASK

如果未配置 LLM，Agent 需要手动分析：

1. 读取 `papers/` 目录下的 PDF 文件
2. 对每篇论文提取关键信息
3. 将分析结果写入 `$PROJECT/.insight/analysis/{id}.json`

**分析文件格式** (`$PROJECT/.insight/analysis/{id}.json`)：
```json
{
  "id": "i0001",
  "title": "Paper Title",
  "summary": "一句话总结",
  "contributions": ["贡献1", "贡献2"],
  "methodology": "方法描述",
  "key_findings": ["发现1", "发现2"],
  "limitations": ["局限性"],
  "tags": ["webagent", "benchmark", "multimodal"],
  "analyzed_at": "2026-01-17T12:00:00Z"
}
```

### Phase 5: 生成增量报告

```bash
# Step 6: 生成/更新索引
insight-pilot index --project $PROJECT
```

报告存储在 `$PROJECT/index.md`，支持增量更新。

**报告结构**：
```markdown
# WebAgent Research Report

> Last updated: 2026-01-17 | Total papers: 42 | New this update: 5

## Overview
研究领域概述，Agent 基于分析结果生成

## Key Themes
- Theme 1: xxx (papers: i0001, i0003)
- Theme 2: xxx (papers: i0005, i0008)

## Paper Summaries

### [Paper Title](papers/i0001.pdf)
- **Authors**: ...
- **Date**: 2026-01-15
- **Summary**: ...
- **Key Contributions**: ...

## Changelog
- 2026-01-17: Added 5 new papers on GUI agents
- 2026-01-10: Initial report with 37 papers
```

---

## 增量更新流程

后续每日/每周更新时：

```bash
# 1. 搜索新论文（使用 --since 限制日期）
insight-pilot search --project $PROJECT --source arxiv --query "web agent" --since 2026-01-17 --limit 20
insight-pilot search --project $PROJECT --source openalex --query "web agent" --since 2026-01-17 --limit 20

# 2. 合并（会追加到已有结果）
insight-pilot merge --project $PROJECT

# 3. 去重（会与已有 items 对比）
insight-pilot dedup --project $PROJECT

# 4. [Agent] 审核新增论文

# 5. 下载新增论文的 PDF
insight-pilot download --project $PROJECT

# 6. [Agent] 分析新论文，更新报告

# 7. 重新生成索引
insight-pilot index --project $PROJECT
```

---

## Project Structure

```
research/myproject/
├── .insight/
│   ├── config.yaml          # 项目配置
│   ├── state.json           # 工作流状态
│   ├── items.json           # 论文元数据（含 status, exclude_reason）
│   ├── raw_arxiv.json       # 原始搜索结果
│   ├── raw_openalex.json
│   ├── download_failed.json # 下载失败列表（供高级下载重试）
│   ├── analysis/            # 论文分析结果
│   │   ├── i0001.json
│   │   ├── i0002.json
│   │   └── ...
│   └── markdown/            # PDF 转换结果（marker）
│       ├── i0001/
│       │   ├── i0001.md     # 转换后的 Markdown
│       │   ├── metadata.json
│       │   └── images/      # 提取的图片
│       └── ...
├── papers/                  # 已下载的 PDF
├── reports/                 # 历史报告存档
└── index.md                 # 当前研究报告（增量更新）
```

## Data Schemas

### Item (Paper)

```json
{
  "id": "i0001",
  "type": "paper",
  "title": "Paper Title",
  "authors": ["Author One", "Author Two"],
  "date": "2026-01-15",
  "abstract": "...",
  "status": "active|excluded|pending",
  "exclude_reason": null,
  "identifiers": {
    "doi": "10.1234/example",
    "arxiv_id": "2601.12345",
    "openalex_id": "W1234567890"
  },
  "urls": {
    "abstract": "https://arxiv.org/abs/2601.12345",
    "pdf": "https://arxiv.org/pdf/2601.12345"
  },
  "download_status": "success|pending|failed|unavailable",
  "local_path": "./papers/i0001.pdf",
  "citation_count": 42,
  "source": ["arxiv", "openalex"],
  "collected_at": "2026-01-17T10:00:00Z"
}
```

## Error Codes

| Code | Meaning | Retryable |
|------|---------|-----------|
| `PROJECT_NOT_FOUND` | Project directory doesn't exist | No |
| `NO_INPUT_FILES` | Required input files missing | No |
| `NO_ITEMS_FILE` | items.json not found | No |
| `INVALID_SOURCE` | Unknown data source | No |
| `NETWORK_ERROR` | API request failed | Yes |
| `RATE_LIMITED` | API rate limit hit | Yes |
| `DOWNLOAD_FAILED` | PDF download failed | Yes |
| `CONVERSION_FAILED` | PDF to Markdown conversion failed | Yes |
| `MISSING_DEPENDENCY` | Required package not installed | No |

## Agent Guidelines

**执行原则**：
- 所有 CLI 命令（init, search, merge, dedup, download, index）都是**自动执行**的，**无需询问用户确认**
- 只有标记为 ⚠️ AGENT TASK 的步骤需要 Agent 介入处理

**具体指引**：
1. **Always use `--json` flag** for structured output
2. **直接执行 CLI 命令**：不要询问"是否要下载 PDF？"等确认问题，按工作流顺序执行即可
3. **审核筛选时**：修改 `items.json` 中的 `status` 和 `exclude_reason` 字段
4. **分析论文时**：为每篇论文创建 `analysis/{id}.json`
5. **生成报告时**：基于 `items.json` 和 `analysis/` 目录生成结构化报告
6. **增量更新时**：只处理新增论文，保留已有分析结果

