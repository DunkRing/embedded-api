# Embedding API

A multilingual text embedding service built with FastAPI, running the [`intfloat/multilingual-e5-large`](https://huggingface.co/intfloat/multilingual-e5-large) model. Deployed on Kubernetes with Keycloak OIDC authentication via oauth2-proxy.

| Component | Details |
|-----------|---------|
| Runtime | Kubernetes (Talos) on Hetzner |
| Gateway | Cilium Gateway API |
| TLS | cert-manager + Let's Encrypt |
| Auth | oauth2-proxy + Keycloak (realm: `skatzi`) |
| Secrets | OpenBao via External Secrets Operator |
| Model cache | Hetzner PVC (`hcloud-volumes`, 10Gi) |
| Image registry | Harbor (`harbor.prod.skatzi.com`) |

---

## Accessing the API

The API is available at:

```
https://embedded-api.prod.skatzi.com
```

### Browser access

Navigate to the URL above. You will be redirected to the Keycloak login page. Sign in with your Skatzi account and you will be forwarded to the interactive Swagger UI at `/docs`.

### API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/embed` | Generate embeddings for a list of texts |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger UI |

### Example request

```bash
curl -X POST https://embedded-api.prod.skatzi.com/embed \
  -H "Content-Type: application/json" \
  -d '{
    "texts": ["Hello world", "Bonjour le monde"],
    "input_type": "passage"
  }'
```

`input_type` can be `"query"` (for search queries) or `"passage"` (for documents). Defaults to `"passage"`.

### Example response

```json
{
  "embeddings": [[0.021, -0.013, "..."], ["..."]],
  "model": "intfloat/multilingual-e5-large",
  "dimensions": 1024,
  "inference_ms": 142.5
}
```

---

## Project structure

```
embedding-api/
├── app/
│   └── main.py             # FastAPI application
├── flux/                   # Kubernetes manifests (GitOps)
│   ├── namespace.yaml
│   ├── deployment.yaml     # Embedding API + oauth2-proxy deployments
│   ├── service.yaml        # Services for both deployments
│   ├── pvc.yaml            # Persistent volume for HuggingFace model cache
│   ├── externalsecret.yaml # Harbor pull secret from OpenBao
│   ├── httproute.yaml      # Gateway API HTTPRoute + ReferenceGrant
│   └── kustomization.yaml
├── .gitea/
│   └── workflows/
│       └── build.yaml      # CI pipeline
├── Containerfile
├── Makefile
└── requirements.txt
```

---

## Local development

**Install dependencies:**
```bash
make install
```

**Run with hot reload:**
```bash
make dev
```

The API will be available at `http://localhost:8000/docs`.

---

## Building and deploying

**Build image locally (native architecture):**
```bash
make build-local
```

**Build and push to Harbor (linux/amd64 for Kubernetes):**
```bash
make push REGISTRY=harbor.prod.skatzi.com IMAGE=library/embedding-api TAG=latest
```

**Apply Kubernetes manifests:**
```bash
kubectl apply -k flux/
```

