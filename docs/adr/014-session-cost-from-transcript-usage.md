# ADR 014: Session Cost from Transcript Token Usage

**Date:** 2026-10-20
**Status:** Accepted

## Context

Claude Code on Vertex AI is billed per token to a shared GCP project. The GCP billing export has no user, IP, or session dimension, and Vertex audit logs record calls but not tokens, so neither can attribute spend to a person or a session. Claude Code's own transcripts do record exact per-call token usage (`message.usage`). MemBridge runs on machines using different endpoints: Vertex on one, the Anthropic API or a Claude subscription on another.

## Decision

1. **Store raw tokens, price at ingest.** One `api_calls` row per API call holds model, auth mode and the token counts by class (input, output, cache read, 5-minute and 1-hour cache writes, web searches), plus a list-price `cost_usd` from `membridge/pricing.toml`. Repricing after a pricing edit is a re-run of `scripts/backfill_usage.py` (~10s for all history); there is no automatic invalidation.
2. **Key calls by the API's (message id, request id).** Claude Code writes one JSONL row per content block, all sharing one `usage`; summing rows roughly doubles cost. Repeats are merged keeping the largest value per field, because an earlier copy can carry a partial output count.
3. **Auth mode decides billing.** Vertex message ids start `msg_vrtx_`, which identifies Vertex calls even in old history. Whether a first-party call is billed (API key) or not (subscription) is not visible in the transcript, so the heartbeat hook reports the session's auth mode from Claude Code's environment (mode only, never a credential) and it is stored on each call. Subscription usage is shown as an API-equivalent figure; history without a mode is classified via the backfill's `--auth-mode` flag.
4. **Re-parse on Stop.** The Stop hook already delivers `transcript_path`; ingest re-parses the main transcript and `<session>/subagents/*.jsonl` and replaces their rows. Measured at ~1s for a 226 MB transcript in a background thread, which is simpler and always correct compared with tracking read offsets.
5. **One price table for all endpoints.** Vertex `global` rates were derived from the billing export (cost / usage per SKU) and match the first-party list prices exactly, with no long-context premium. Fast mode (first-party only) is priced from `usage.speed`; Haiku 5.5's long-prompt tier per call.

## Consequences

- Cost is per machine: it covers transcripts on this host only. Vertex spend from other machines on the same project is not seen.
- It is an estimate at list price. Negotiated discounts, regional Vertex endpoints (~10% premium), US-only inference (1.1x) and anything not in the transcript are not reflected.
- Models missing from `pricing.toml` are stored and counted as unpriced; add the model and re-run the backfill.
- An `apiKeyHelper`-only setup (no key in the environment) is reported as `subscription`.
