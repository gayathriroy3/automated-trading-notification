# High level architecture:

[Architecture High Level](portfolio_project_high_level.png)


# Configuration


## 1. Which LLM powers every agent -- `llm_config.yaml`

The parser, validator, explainer, and news-sentiment agents all call the
model through one shared interface.

```yaml
llm:
  provider: gemini
  model: models/gemini-2.5-flash
  api_key_env: GEMINI_API_KEY
```
## 2. Which news resources the sentiment agent checks -- `news_sources_config.yaml`

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

**Adding a resource type that isn't built in** 
```python
from agents.news.aggregator import register_source_type
register_source_type("my_resource", lambda: MyResourceSource)
```
then set `type: my_resource` in a `news_sources` block.
