import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qdrant_client.models import Filter, FieldCondition, MatchValue
from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.core.qdrant_client import qdrant_client
from app.retrieval.qdrant_setup import COLLECTION_NAME
from app.repository.models import Document


async def migrate():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Document))
        docs = result.scalars().all()

        for doc in docs:
            await qdrant_client.set_payload(
                collection_name=COLLECTION_NAME,
                payload={"is_active": doc.is_active},
                points=Filter(
                    must=[FieldCondition(key="document_id", match=MatchValue(value=str(doc.id)))]
                ),
            )
            print(f"Đã cập nhật is_active={doc.is_active} cho document '{doc.title}'")

    print(f"\nHoàn tất migrate {len(docs)} document.")


if __name__ == "__main__":
    asyncio.run(migrate())