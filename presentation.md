# Embedded API
### A multilingual text embedding service

---

## What is it?

A REST API that turns text into **vector embeddings**

- Wraps the `intfloat/multilingual-e5-large` model from HuggingFace
- 1024-dimensional float vectors
- Supports **50+ languages** out of the box
- Built with FastAPI + PyTorch
---

## Stack Summary

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Framework | FastAPI + uvicorn |
| ML | PyTorch + HuggingFace Transformers |
| Container | Podman / Kaniko |
| Orchestration | Kubernetes (Talos) |
| Ingress | Cilium Gateway API |
| Auth | oauth2-proxy + Keycloak |
| Registry | Harbor |
| Secrets | OpenBao + External Secrets |
| Infra | Hetzner Cloud |
| CI/CD | Gitea Actions |

---

## What are embeddings useful for?

Converting text into numbers that capture **semantic meaning**

- Semantic search — find documents by meaning, not keywords
- Similarity comparison — "cat" and "kitten" end up close together
- RAG pipelines — retrieve relevant context for LLMs
- Classification, clustering, recommendations


---

## What's in the code

**Functions:**
- `lifespan(app)` — loads model + tokenizer at startup, releases on shutdown; failure stops the app
- `unhandled_exception_handler(request, exc)` — global catch-all; logs stack trace, returns safe 500
- `texts_must_be_non_empty_strings(texts)` — Pydantic validator; rejects blank or oversized texts
- `average_pool(last_hidden_state, attention_mask)` — collapses token embeddings into one vector per text
- `embed(request)` — prefixes texts, runs tokenizer + model, normalises output, returns embeddings
- `health()` — checks model/tokenizer are loaded; returns 503 if not

**Error handling & observability:**
- 503 if model isn't loaded, 500 if inference fails, 422 with field-level detail for bad input
- Global exception handler catches anything else and returns a generic safe message
- Structured logging on model load, every request (batch size, inference ms), and all errors

---

## Containerfile

Multi-stage build keeps the image lean

```dockerfile
# Stage 1 — builder
FROM python:3.12-slim AS builder
RUN pip install --prefix=/install -r requirements.txt

# Stage 2 — runtime
FROM python:3.12-slim
COPY --from=builder /install /usr/local
RUN useradd -u 1000 appuser
USER appuser
```

- Only production deps in the final image
- Runs as **non-root** (UID 1000)
- Built-in health check hits `/health` every 30s

---

## CI/CD Pipeline

Two jobs on every push to `main`: **lint → build**

```
push to main
    │
    ▼
┌─────────┐     ┌───────────────────────────────┐
│  lint   │ ──▶ │  build & push (Kaniko)        │
│  ruff   │     │  harbor.prod.skatzi.com/...   │
└─────────┘     └───────────────────────────────┘
```

Build only runs if lint passes.

---

## Lint job

Uses `ruff` — fast Python linter & formatter

```yaml
- run: ruff check app/
- run: ruff format --check app/
```

Any style or lint error **blocks the build**.

---

## Build job (Kaniko)

Runs inside a Kaniko container — no Docker daemon needed

1. Writes Harbor credentials to `/kaniko/.docker/config.json`
2. Downloads source archive from Gitea API
3. Runs `executor` — builds & pushes two tags:
   - `:latest`
   - `:<git-sha>` — every commit is traceable

Secrets (`HARBOR_USERNAME`, `HARBOR_PASSWORD`, `GITEA_TOKEN`)
are injected via Gitea Actions secrets.

---

## How the app gets deployed

```
  Gitea ──── CI ──────────────────▶ Harbor
    │                                  ▲
    │  (flux/ manifests)               │ (image pull)
    │                                  │
    └──────── Flux                     │
                │                      │
                ▼                      │
     ┌─────────────────────┐           │
     │  Kubernetes Cluster │           │
     │  - Deployment ──────────────────┘
     │  - Service          │
     │  - HTTPRoute        │
     │  - PVC              │
     │  - ExternalSecrets  │
     └─────────────────────┘
```

---

## Secrets Management

No secrets hardcoded anywhere — all via **OpenBao** (open-source Vault)

```
OpenBao (external vault)
       │
       ▼
External Secrets Operator
       │
       ├──▶ harbor-registry-secret   (image pull)
       └──▶ oauth2-proxy secrets     (client-id, secret, cookie)
```

Secrets sync every **1 hour** automatically.

---

## Deployment Strategy

Uses `Recreate` (not `RollingUpdate`)

- Old pod is **fully stopped** before new one starts
- Avoids two pods competing for the same GPU or memory
- Means a brief downtime window during deploys
- Acceptable trade-off for a heavy ML workload
