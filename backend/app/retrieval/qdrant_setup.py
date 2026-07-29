from qdrant_client.models import Distance, VectorParams

from app.core.qdrant_client import qdrant_client, EMBEDDING_DIM

COLLECTION_NAME = "document_chunks"


async def ensure_collection_exists():
    collections = await qdrant_client.get_collections()
    existing = [c.name for c in collections.collections]

    if COLLECTION_NAME not in existing:
        await qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        print(f"Đã tạo collection '{COLLECTION_NAME}'")
    else:
        print(f"Collection '{COLLECTION_NAME}' đã tồn tại")