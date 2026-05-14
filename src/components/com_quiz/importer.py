"""Import questions from the legacy JSON format into the database."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from .models import QuizAnswer, QuizQuestion
from .service import (
    build_category_payload,
    build_question_payload,
    create_category,
    create_question,
    get_category_by_slug,
)


async def import_from_json(db: AsyncSession, path: Path) -> dict:
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
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("JSON musí být pole objektů.")

    stats: dict = {"created": 0, "errors": 0, "first_error": ""}
    category_cache: dict[str, int] = {}

    # Pass 1: create all unique categories up front (single transaction context)
    cat_names: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name = str(item.get("category", "Ostatní")).strip() or "Ostatní"
        if name not in seen:
            cat_names.append(name)
            seen.add(name)

    for cat_name in cat_names:
        try:
            payload = build_category_payload(
                name=cat_name, slug="", description="", icon="", sort_order=0,
            )
            cat = await get_category_by_slug(db, payload.slug)
            if cat is None:
                cat = await create_category(db, payload)
            category_cache[cat_name] = cat.id
        except Exception as exc:
            if not stats["first_error"]:
                stats["first_error"] = f"Kategorie '{cat_name}': {exc!r}"

    if not category_cache:
        raise ValueError(stats["first_error"] or "Nepodařilo se vytvořit žádnou kategorii.")

    await db.flush()

    # Pass 2: import questions — each row in its own savepoint so one failure
    # doesn't corrupt the session state for subsequent rows
    for item in raw:
        try:
            cat_name = str(item.get("category", "Ostatní")).strip() or "Ostatní"
            category_id = category_cache.get(cat_name)
            if category_id is None:
                raise ValueError(f"Kategorie '{cat_name}' nebyla vytvořena.")

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
            async with db.begin_nested():
                await create_question(db, payload_q)
            stats["created"] += 1
        except Exception as exc:
            stats["errors"] += 1
            if not stats["first_error"]:
                stats["first_error"] = repr(exc)

    await db.commit()
    return stats


async def import_from_json_upsert(db: AsyncSession, path: Path) -> dict:
    """Same as import_from_json but clears all existing questions first."""
    await db.execute(delete(QuizAnswer))
    await db.execute(delete(QuizQuestion))
    await db.flush()
    return await import_from_json(db, path)
