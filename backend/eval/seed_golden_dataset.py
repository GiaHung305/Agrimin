import asyncio
import json
import os
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.db import AsyncSessionLocal
from app.repository.models import GoldenDataset


DATASET_PATH = Path(__file__).with_name("golden_dataset_seed.json")


async def seed() -> None:
    payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    version = payload["version"] if isinstance(payload, dict) else "v1"
    items = payload["items"] if isinstance(payload, dict) else payload

    created = 0
    async with AsyncSessionLocal() as db:
        for item in items:
            existing = await db.execute(
                select(GoldenDataset.id).where(
                    GoldenDataset.dataset_version == version,
                    GoldenDataset.question == item["question"],
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue
            db.add(
                GoldenDataset(
                    question=item["question"],
                    expected_answer=item["expected_answer"],
                    expected_citation=item.get("expected_citation"),
                    category=item["category"],
                    created_by="dev-seed",
                    dataset_version=version,
                )
            )
            created += 1
        await db.commit()

    print(f"Seeded {created}/{len(items)} evaluation items for dataset {version}")


if __name__ == "__main__":
    asyncio.run(seed())
