# ADR 007: Vertex AI Authentication

**Date:** 2026-06-23  
**Status:** Superseded by [ADR 012](012-drop-docker-native-process.md) (Docker removed; ADC now works natively)

## Context

`summariser.py` supports two backends: the standard Anthropic API (default) and Vertex AI (`USE_VERTEX=1`). When using Vertex, the process needs GCP credentials to authenticate with `AnthropicVertex`.

## Decision

Use Application Default Credentials (ADC) via `gcloud auth application-default login`. Since MemBridge runs natively on the host (not in Docker), the ADC directory is automatically available - no mount or extra config needed beyond setting `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_REGION` in `.env`.

## Why not a service account?

A dedicated service account with Vertex AI User role is the correct approach for anything beyond a personal dev machine - scoped credentials, no dependency on the developer's personal login, rotatable. ADC is fine for local single-developer use.

## Consequences

- ADC token expiry silently breaks auto-summary - run `gcloud auth application-default login` to refresh
- Most users will use the standard Anthropic API (`ANTHROPIC_API_KEY`) and never need this
