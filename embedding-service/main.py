from fastapi import FastAPI
from pydantic import BaseModel
import torch
from sentence_transformers import SentenceTransformer
from sentence_transformers import CrossEncoder

app = FastAPI(title="AgriMind Embedding Service")

device = "cuda" if torch.cuda.is_available() else "cpu"
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


reranker = CrossEncoder("BAAI/bge-reranker-v2-m3", device=device)


class RerankRequest(BaseModel):
    query: str
    documents: list[str]


class RerankResponse(BaseModel):
    scores: list[float]


@app.post("/rerank", response_model=RerankResponse)
async def rerank(req: RerankRequest):
    pairs = [[req.query, doc] for doc in req.documents]
    scores = reranker.predict(pairs).tolist()
    return {"scores": scores}