"""Import questions from the legacy JSON format into the database."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from .service import (
    build_category_payload,
    build_question_payload,
    create_category,
    create_question,
    get_category_by_slug,
    get_question,
    update_category,
    update_question,
)
from .models import QuizQuestion, QuizAnswer
from sqlalchemy import select, delete


async def import_from_json(db: AsyncSession, path: Path) -> dict[str, int]:
    """Import questions from a legacy JSON file.

    Expected format:
    [
      {
        "question": "Text otázky",
        "answers": ["Odpověď A", "Odpověď B", "Odpověď C", "Odpověď D"],
        "correct": 0,
        "category": "Název kategorie",
        "info": "Vysvětlení pro nesprávnou odpověď"
      },
      ...
    ]
    Returns a dict with counts: {"created": N, "skipped": N, "errors": N}.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("JSON must be a list of question objects.")

    stats: dict[str, int] = {"created": 0, "skipped": 0, "errors": 0}
    category_cache: dict[str, int] = {}

    for item in raw:
        try:
            cat_name = str(item.get("category", "Ostatní")).strip() or "Ostatní"
            if cat_name not in category_cache:
                payload = build_category_payload(
                    name=cat_name,
                    slug="",
                    description="",
                    icon="",
                    sort_order=0,
                )
                cat = await get_category_by_slug(db, payload.slug)
                if cat is None:
                    cat = await create_category(db, payload)
                category_cache[cat_name] = cat.id
            category_id = category_cache[cat_name]

            question_text = str(item.get("question", "")).strip()
            answers_raw = [str(a) for a in item.get("answers", [])]
            correct_index = int(item.get("correct", 0))
            explanation = str(item.get("info", "")).strip()

            payload_q = build_question_payload(
                category_id=category_id,
                text=question_text,
                explanation=explanation,
                sort_order=0,
                answer_texts=answers_raw,
                correct_index=correct_index,
            )
            await create_question(db, payload_q)
            stats["created"] += 1
        except Exception:
            stats["errors"] += 1

    await db.commit()
    return stats


async def import_from_json_upsert(db: AsyncSession, path: Path) -> dict[str, int]:
    """Same as import_from_json but clears all existing questions first."""
    await db.execute(delete(QuizAnswer))
    await db.execute(delete(QuizQuestion))
    await db.flush()
    return await import_from_json(db, path)
