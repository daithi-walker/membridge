# ADR 007: Vertex ADC Credentials via Volume Mount

**Date:** 2026-06-23  
**Status:** Accepted (interim — not desired state)

## Context

The auto-summariser calls Claude via the Anthropic SDK, configured to use Vertex AI as the backend (`AnthropicVertex`). Inside Docker, the process needs GCP credentials to authenticate with Vertex.

## Decision

The host's Application Default Credentials (ADC) directory is volume-mounted into the container:

```yaml
volumes:
  - "${HOME}/.config/gcloud:/root/.config/gcloud:ro"
```

The `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_REGION` env vars are set in `.env` and passed through via `docker-compose.yml`.

## Why not a service account?

A dedicated service account with Vertex AI User role would be the correct production approach — scoped credentials, no dependency on the developer's personal login, rotatable. This was explicitly deferred: *"ideally we'd use a service account for this and not my full credentials but let's leave it for now."*

The ADC mount works for a single-developer local tool and requires no key management. It does break if the user's ADC token expires and isn't refreshed (`gcloud auth application-default login`).

## Desired state

- Service account JSON key stored in `.env` (gitignored), mounted as `GOOGLE_APPLICATION_CREDENTIALS`
- Or: drop Docker entirely (see ADR 004), at which point the host process uses ADC natively with no mount needed

## Consequences

- ADC expiry silently breaks auto-summary — no error surfaced in the UI
- The container runs as root with read access to `~/.config/gcloud` — acceptable for a local dev tool
- ADC mount path (`/root/.config/gcloud`) assumes the container user is root; would break with a non-root container user
