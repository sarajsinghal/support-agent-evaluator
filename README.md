# Project 10 — AI Customer Support Agent Evaluation & Benchmarking Platform

A Streamlit portfolio application for evaluating customer support responses from uploaded transcripts or a user-configured live agent endpoint. It combines transparent Python heuristics with an optional OpenAI-compatible LLM-as-a-judge adapter. A local SQLite database stores run summaries, case results, human reviews, and audit events.

## Features

- CSV, JSON, and TXT transcript ingestion (8 MB per upload limit).
- Live API testing with configurable endpoint, bearer token or API-key header, bounded timeouts, redirect blocking, response-size limits, and basic private-network URL blocking.
- Scenario library for e-commerce, shipment, refunds, account support, general customer service, and adversarial prompt injection, with Hindi, English, and Hinglish starter cases.
- Rubric dimensions: accuracy, grounding, policy compliance, empathy, resolution, relevance, consistency, privacy/security, and injection resistance.
- Reference answers, policy context, expected phrases, prohibited phrases, evidence severity, explanations, and pass/fail/needs-review outcomes.
- Optional OpenAI-compatible chat completions judge. Provider, model, and key are user supplied; credentials are held only in session memory and never stored in run history.
- Human review overrides and notes, version comparisons, benchmark dashboard, and PDF/CSV/Excel/JSON exports.
- SQLite evaluation history and audit trail.

## Windows setup

Open PowerShell in this folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app.py
```

Open the local URL printed by Streamlit. `.env` is ignored by Git. The judge fields in the sidebar can also be entered at run time and are not persisted.

## Use

1. Choose offline transcripts or live endpoint in the sidebar.
2. For offline evaluation, upload your own CSV/JSON/TXT file. JSON supports a list of records with `customer` and `agent_response` fields, or `messages` entries containing `role` and `content`. CSV accepts columns such as `customer`, `agent_response`, `reference_answer`, `policy`, `must_include`, `must_not_include`, `language`, `category`, and `version`. TXT uses blank-line-separated `Customer:` and `Agent:` turns.
3. Provide a version label and optionally configure an LLM judge. A judge call transmits the selected conversation and context to the endpoint you configure; do not enable it for content you are not authorized to share.
4. Click **Run evaluation**. For live mode, use a test agent and endpoint; requests send both `message` and `input` string keys. Responses may be JSON with `response`, `answer`, `message`, `output`, or `text`.
5. Inspect the evidence, review cases, add a human decision and notes, compare runs, and export a report.

## Security and evaluation limits

Uploaded transcripts are processed in memory and are not written to disk by ingestion. They are included in local SQLite run history only when the user clicks Run. Live requests are sent only to the configured endpoint after explicit run action. Optional judge requests send case and response data to the configured provider. Auth secrets are not included in database records or exports. API calls use timeouts, disallow redirects, cap response bodies, and reject obvious local/private IP targets; deploy behind suitable outbound network controls for stronger SSRF protection. The endpoint adapter uses a generic JSON request shape; adapt `call_agent` for your agent's documented contract.

Deterministic checks are heuristic and can miss nuance. LLM-as-a-judge scores are probabilistic and may be inconsistent or wrong. Require human review for high-impact decisions. This tool does not certify compliance, and no performance metric should be treated as representative without a carefully designed benchmark.

## Tests

```powershell
pytest -q
```

The tests cover parsing, upload limits, evaluation flags, endpoint safety checks, and review/audit persistence.

## Deployment

### GitHub + Streamlit Community Cloud

This project is structured for the repository root: `app.py`, `requirements.txt`, `.streamlit/config.toml`, and the `support_eval/` package. The `.gitignore` intentionally excludes all files in `samples/`, local databases, temporary work, virtual environments, and secrets. Do not add test transcripts or credentials to the repository.

1. Create a **private** GitHub repository and publish this project from GitHub Desktop or Git. Keep the repository private so viewers cannot browse or clone the source.
2. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) with GitHub and grant it access to the private repository. Choose **Create app**, then select this repository, the `main` branch, and `app.py` as the entrypoint.
3. Keep the Streamlit app private in its Sharing settings. Invite viewers by email; do not give them GitHub repository access unless they should be able to change the code. Streamlit Community Cloud currently permits one private app per account.
4. Add any provider secrets in the app's Streamlit secrets settings, never in GitHub. This app's judge fields can also be entered at runtime and are not written into run history.
5. Test a small, non-sensitive transcript after deployment. The SQLite database is local to the running app and may not provide durable history across rebuilds or restarts; use managed storage if durable multi-user history is required.

Streamlit deploys the selected branch and applies later GitHub commits to the app. Keep write access limited to yourself or trusted maintainers. Viewers cannot directly edit the source when the GitHub repo is private and they have only Streamlit viewer access. A private app restricts app access; a public app can still use a private source repository, but anyone who can use it can inspect its behavior and may reproduce its functionality.

For other trusted Streamlit-compatible hosts, limit outbound access to approved agent and judge providers, protect persistent databases and backups, set retention controls, and use non-production test data when possible. For multi-user production deployment, replace local SQLite with a managed database, add identity and role-based access, and configure outbound egress controls. Never publish real provider keys in repository files.
