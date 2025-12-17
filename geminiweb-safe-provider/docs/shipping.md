# Shipping Milestone 1 (Shippability Review)

## Ship Criteria (M1)

- Local server starts and responds to `GET /healthz`
- `POST /v1/chat/completions` returns OpenAI-shaped JSON when configured with a valid `GOOGLE_API_KEY`
- Clear behavior when not configured (returns OpenAI-shaped `authentication_error`)
- Offline unit tests pass
- No web UI reverse engineering code paths exist

## Risks (M1)

- Upstream contract drift (`v1beta`)
- 429/quotas and retry behavior (respect `Retry-After`)
- Message mapping fidelity vs. OpenAI semantics (subset only)

## Final Checklist

- [ ] `pip install -e ".[dev,server,release]"` succeeds
- [ ] `pytest -q` passes offline (or CI is green)
- [ ] `ruff check .` and `mypy src` pass (or CI is green)
- [ ] `python -m build` and `twine check dist/*` pass (or CI is green)
- [ ] `python3 -m uvicorn geminiweb_provider.server:app ...` starts
- [ ] `curl /healthz` returns `{"status":"ok"}`
- [ ] `curl /v1/chat/completions` returns:
  - 401 with `{"error":{"type":"authentication_error",...}}` if `GOOGLE_API_KEY` missing
  - 200 with `{"object":"chat.completion",...}` when `GOOGLE_API_KEY` is valid

## Recorded Commands (this repo)

```bash
cd geminiweb-safe-provider
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[dev,server,release]"
pytest -q
ruff check .
mypy src
python -m build
python -m twine check dist/*
```

Expected output: all checks pass.

## Rollout Plan

1. Run locally with a real `GOOGLE_API_KEY` and smoke-test `/v1/chat/completions`
2. Deploy behind a private network / auth proxy if exposing beyond localhost
3. Monitor:
   - 401 rates (misconfig)
   - 429 rates (quota)
   - 5xx retries (upstream instability)
4. If needed, tune `.env`:
   - `UPSTREAM_MAX_ATTEMPTS`, `UPSTREAM_BACKOFF_*`, `UPSTREAM_TIMEOUT_SECONDS`
