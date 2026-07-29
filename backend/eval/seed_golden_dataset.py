import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.db import AsyncSessionLocal
from app.repository.models import GoldenDataset


async def seed():
    with open("eval/golden_dataset_seed.json", encoding="utf-8") as f:
        data = json.load(f)

    async with AsyncSessionLocal() as db:
        for item in data:
            entry = GoldenDataset(
                question=item["question"],
                expected_answer=item["expected_answer"],
                expected_citation=item.get("expected_citation"),
                category=item["category"],
                created_by="dev-seed",
            )
            db.add(entry)
        await db.commit()

    print(f"Đã seed {len(data)} câu hỏi vào golden_dataset")


if __name__ == "__main__":
    asyncio.run(seed())