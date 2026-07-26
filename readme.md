# High level architecture:

[alt text](portfolio_project_high_level.png)


# Configuration

Two independent things are config-driven in this project. Neither requires
touching agent code.

## 1. Which LLM powers every agent -- `llm_config.yaml`

The parser, validator, explainer, and news-sentiment agents all call the
model through one shared interface (`agents/llm/base.py`). Which real
provider sits behind that interface is decided entirely by
`config/llm_config.yaml`:

```yaml
llm:
  provider: gemini          # gemini | openai | anthropic (alias: claude)
  model: models/gemini-2.5-flash
  api_key_env: GEMINI_API_KEY
```

To switch providers, edit this file (or point `LLM_CONFIG_PATH` at a
different one) and set the matching API key in your environment / `.env`.
No code changes. See the commented examples in the file for Claude and
OpenAI.

**Adding a provider that isn't built in** (a self-hosted model, a vendor
not covered by the OpenAI-compatible adapter, etc.): implement
`agents.llm.base.LLMClient` (one method, `generate(system, user) -> str`)
and register it:

```python
from agents.llm.factory import register_provider
register_provider("my_provider", lambda: MyProviderClass)
```

then set `provider: my_provider` in the config.

## 2. Which news resources the sentiment agent checks -- `news_sources_config.yaml`

`agents/sentiment/sentiment_agent.py` never names a resource. At trigger
time it asks `agents/news/aggregator.py` for headlines; the aggregator
builds exactly the resources listed (and enabled) in
`config/news_sources_config.yaml`, fetches from each, dedupes, and caps
the total before handing them to the LLM.

```yaml
news_sources:
  - type: yahoo_finance
    enabled: true
    limit: 5
  - type: rss
    name: moneycontrol_markets
    enabled: true
    url: https://www.moneycontrol.com/rss/marketreports.xml
    filter_by_instrument: true
```

To add a resource: add a block. To remove one: delete it (or set
`enabled: false` to pause without deleting). To reconfigure one: edit its
fields. Built-in types live in `agents/news/sources/`:

| type          | what it is                                            |
|---------------|--------------------------------------------------------|
| `yahoo_finance` | Per-ticker headlines via `yfinance` (the original/default source) |
| `rss`         | Any RSS/Atom feed URL, optionally filtered to items mentioning the instrument |
| `newsapi`     | [NewsAPI.org](https://newsapi.org) search, needs an API key |
| `static_file` | Headlines read from a local JSON file -- offline/curated resource, also used by the automated tests |

**Adding a resource type that isn't built in** (a broker's proprietary
feed, a Bloomberg export, an internal research tool): implement
`agents.news.base.NewsSource` (one method,
`fetch(instrument, limit) -> list[NewsItem]`, must never raise) and
register it:

```python
from agents.news.aggregator import register_source_type
register_source_type("my_resource", lambda: MyResourceSource)
```

then set `type: my_resource` in a `news_sources` block.

## Environment variables

Copy `.env.example` at the project root to `.env` and fill in whichever
keys the providers/resources you've enabled actually need. Only the ones
referenced by an *enabled* provider or resource are required.
