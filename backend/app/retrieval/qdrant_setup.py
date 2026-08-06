import logging

from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

from app.core.qdrant_client import qdrant_client, EMBEDDING_DIM

COLLECTION_NAME = "document_chunks"
logger = logging.getLogger(__name__)


async def ensure_collection_exists():
    collections = await qdrant_client.get_collections()
    existing = [c.name for c in collections.collections]

    if COLLECTION_NAME not in existing:
        await qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection '%s'", COLLECTION_NAME)
    else:
        logger.debug("Qdrant collection '%s' already exists", COLLECTION_NAME)

    # Retrieval filters active chunks; document replacement and deactivation
    # filter by document_id. Index both fields so filtering scales with corpus.
    await qdrant_client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="is_active",
        field_schema=PayloadSchemaType.BOOL,
        wait=True,
    )
    await qdrant_client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="document_id",
        field_schema=PayloadSchemaType.KEYWORD,
        wait=True,
    )
