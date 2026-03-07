import logging
import time
from contextlib import asynccontextmanager
from typing import Literal

import torch
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from transformers import AutoModel, AutoTokenizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MODEL_NAME = "intfloat/multilingual-e5-large"
MAX_TEXTS = 64
MAX_TEXT_LENGTH = 10_000

tokenizer: AutoTokenizer | None = None
model: AutoModel | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global tokenizer, model
    logger.info("Loading model: %s", MODEL_NAME)
    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        model = AutoModel.from_pretrained(MODEL_NAME)
        model.eval()
        logger.info("Model loaded successfully")
    except Exception:
        logger.exception("Failed to load model")
        raise
    yield
    logger.info("Shutting down, releasing model")
    del model, tokenizer


app = FastAPI(title="Embedding API", lifespan=lifespan)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=MAX_TEXTS)
    input_type: Literal["query", "passage"] = "passage"

    @field_validator("texts")
    @classmethod
    def texts_must_be_non_empty_strings(cls, texts: list[str]) -> list[str]:
        for i, text in enumerate(texts):
            if not text or not text.strip():
                raise ValueError(f"texts[{i}] must not be blank")
            if len(text) > MAX_TEXT_LENGTH:
                raise ValueError(
                    f"texts[{i}] exceeds max length of {MAX_TEXT_LENGTH} characters"
                )
        return texts


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    model: str
    dimensions: int
    inference_ms: float


def average_pool(
    last_hidden_state: torch.Tensor, attention_mask: torch.Tensor
) -> torch.Tensor:
    mask_expanded = attention_mask.unsqueeze(-1).float()
    return (last_hidden_state * mask_expanded).sum(dim=1) / mask_expanded.sum(
        dim=1
    ).clamp(min=1e-9)


@app.post("/embed", response_model=EmbedResponse)
async def embed(request: EmbedRequest):
    if model is None or tokenizer is None:
        logger.error("Embed called but model is not loaded")
        raise HTTPException(status_code=503, detail="Model not available")

    logger.info(
        "Embedding %d texts with input_type=%s", len(request.texts), request.input_type
    )

    prefixed = [f"{request.input_type}: {t}" for t in request.texts]

    try:
        encoded = tokenizer(
            prefixed,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )

        t0 = time.perf_counter()
        with torch.no_grad():
            outputs = model(**encoded)
        inference_ms = (time.perf_counter() - t0) * 1000

    except Exception:
        logger.exception("Inference failed")
        raise HTTPException(status_code=500, detail="Embedding inference failed")

    embeddings = average_pool(outputs.last_hidden_state, encoded["attention_mask"])
    embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

    logger.info("Inference completed in %.1fms", inference_ms)

    return EmbedResponse(
        embeddings=embeddings.tolist(),
        model=MODEL_NAME,
        dimensions=embeddings.shape[-1],
        inference_ms=round(inference_ms, 2),
    )


@app.get("/health")
async def health():
    ready = model is not None and tokenizer is not None
    if not ready:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "ok", "model": MODEL_NAME}
