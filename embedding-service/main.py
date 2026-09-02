import asyncio
import logging
import os

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import CrossEncoder, SentenceTransformer

app = FastAPI(title="AgriMind Embedding Service")
logger = logging.getLogger(__name__)


def _resolve_device(variable: str, fallback: str) -> str:
    requested = os.getenv(variable, fallback).lower()
    if requested == "cuda" and not torch.cuda.is_available():
        logger.warning("%s=cuda requested but CUDA is unavailable; using CPU", variable)
        return "cpu"
    return requested


embedding_device = _resolve_device(
    "EMBEDDING_DEVICE",
    "cuda" if torch.cuda.is_available() else "cpu",
)
reranker_device = _resolve_device("RERANKER_DEVICE", embedding_device)
reranker_model_name = os.getenv(
    "RERANKER_MODEL",
    "BAAI/bge-reranker-v2-m3",
).strip()
if not reranker_model_name:
    raise ValueError("RERANKER_MODEL must not be blank")
device = embedding_device
embedding_semaphore = asyncio.Semaphore(
    max(1, int(os.getenv("EMBEDDING_MAX_CONCURRENCY", "1")))
)
reranker_semaphore = asyncio.Semaphore(
    max(1, int(os.getenv("RERANKER_MAX_CONCURRENCY", "1")))
)
model = SentenceTransformer("BAAI/bge-m3", device=device)
logger.info("Embedding model loaded on %s", device)


class EmbedRequest(BaseModel):
    texts: list[str]


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    device: str


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest):
    async with embedding_semaphore:
        vectors = await asyncio.to_thread(
            model.encode,
            req.texts,
            normalize_embeddings=True,
        )
    return {"embeddings": vectors.tolist(), "device": device}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "device": device,
        "reranker_device": reranker_device,
        "reranker_model": reranker_model_name,
    }


reranker = CrossEncoder(reranker_model_name, device=reranker_device)
logger.info("Reranker model %s loaded on %s", reranker_model_name, reranker_device)


class RerankRequest(BaseModel):
    query: str
    documents: list[str]
    expected_model: str


class RerankResponse(BaseModel):
    scores: list[float]
    model: str


class RerankBatchItem(BaseModel):
    query: str
    documents: list[str] = Field(min_length=1, max_length=4)


class RerankBatchRequest(BaseModel):
    items: list[RerankBatchItem] = Field(min_length=1, max_length=4)
    expected_model: str


class RerankBatchResponse(BaseModel):
    scores: list[list[float]]
    model: str


def _require_expected_reranker(expected_model: str) -> None:
    if expected_model != reranker_model_name:
        raise HTTPException(
            status_code=409,
            detail="Configured reranker does not match the loaded model",
        )


@app.post("/rerank", response_model=RerankResponse)
async def rerank(req: RerankRequest):
    _require_expected_reranker(req.expected_model)
    pairs = [[req.query, doc] for doc in req.documents]
    # CrossEncoder logits are model-specific and cannot be compared directly
    # with a confidence threshold.  Make this API's contract explicit: every
    # rerank score is a relevance probability in the [0, 1] interval.
    async with reranker_semaphore:
        scores = await asyncio.to_thread(
            reranker.predict,
            pairs,
            activation_fn=torch.nn.Sigmoid(),
        )
    return {"scores": scores, "model": reranker_model_name}


@app.post("/rerank/batch", response_model=RerankBatchResponse)
async def rerank_batch(req: RerankBatchRequest):
    _require_expected_reranker(req.expected_model)
    pairs: list[list[str]] = []
    lengths: list[int] = []
    for item in req.items:
        lengths.append(len(item.documents))
        pairs.extend([[item.query, document] for document in item.documents])
    async with reranker_semaphore:
        flattened = await asyncio.to_thread(
            reranker.predict,
            pairs,
            activation_fn=torch.nn.Sigmoid(),
        )
    grouped: list[list[float]] = []
    offset = 0
    for length in lengths:
        grouped.append([float(score) for score in flattened[offset : offset + length]])
        offset += length
    return {"scores": grouped, "model": reranker_model_name}
