# trading-agent

A personal research agent that watches a Schwab account and emails recommendations.
**It never places trades.** You decide and trade yourself.

- Design: [docs/SPEC.md](docs/SPEC.md)
- Emails: [docs/EMAILS.md](docs/EMAILS.md)
- Build phases: [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md)

## Setup

```bash
uv sync --python 3.12
cp config.local.example.yaml config.local.yaml   # then fill in your addresses
uv run tradeagent init-db
uv run tradeagent doctor
```

Store secrets in the macOS Keychain. You are prompted for the value, which is not shown as you type:

```bash
uv run tradeagent set-secret gmail_app_password
```

Every approved number lives in `config.yaml`. Run the tests with `uv run pytest`.
