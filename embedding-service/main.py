from fastapi import FastAPI
from pydantic import BaseModel
import os
import torch
from sentence_transformers import SentenceTransformer
from sentence_transformers import CrossEncoder

app = FastAPI(title="AgriMind Embedding Service")

def _resolve_device(variable: str, fallback: str) -> str:
    requested = os.getenv(variable, fallback).lower()
    if requested == "cuda" and not torch.cuda.is_available():
        print(f"{variable}=cuda requested but CUDA is unavailable; using CPU instead.")
        return "cpu"
    return requested


embedding_device = _resolve_device("EMBEDDING_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
reranker_device = _resolve_device("RERANKER_DEVICE", embedding_device)
device = embedding_device
model = SentenceTransformer("BAAI/bge-m3", device=device)
print(f"Embedding model đã tải lên: {device}")


class EmbedRequest(BaseModel):
    texts: list[str]


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    device: str


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest):
    vectors = model.encode(req.texts, normalize_embeddings=True).tolist()
    return {"embeddings": vectors, "device": device}


@app.get("/health")
async def health():
    return {"status": "ok", "device": device}


reranker = CrossEncoder("BAAI/bge-reranker-v2-m3", device=reranker_device)


class RerankRequest(BaseModel):
    query: str
    documents: list[str]


class RerankResponse(BaseModel):
    scores: list[float]


@app.post("/rerank", response_model=RerankResponse)
async def rerank(req: RerankRequest):
    pairs = [[req.query, doc] for doc in req.documents]
    # CrossEncoder logits are model-specific and cannot be compared directly
    # with a confidence threshold.  Make this API's contract explicit: every
    # rerank score is a relevance probability in the [0, 1] interval.
    scores = reranker.predict(pairs, activation_fn=torch.nn.Sigmoid()).tolist()
    return {"scores": scores}
