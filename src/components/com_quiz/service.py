from __future__ import annotations

import random
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    QuizAnswer,
    QuizAttempt,
    QuizAttemptAnswer,
    QuizCategory,
    QuizQuestion,
    QuizTest,
)


class QuizError(ValueError):
    def __init__(self, key: str, **kwargs: Any) -> None:
        super().__init__(key)
        self.key = key
        self.kwargs = kwargs


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------

async def list_categories(db: AsyncSession) -> list[QuizCategory]:
    result = await db.execute(select(QuizCategory).order_by(QuizCategory.sort_order, QuizCategory.name))
    return list(result.scalars().all())


async def get_category(db: AsyncSession, category_id: int) -> QuizCategory | None:
    return await db.get(QuizCategory, category_id)


async def get_category_by_slug(db: AsyncSession, slug: str) -> QuizCategory | None:
    result = await db.execute(select(QuizCategory).where(QuizCategory.slug == slug))
    return result.scalar_one_or_none()


@dataclass(frozen=True)
class CategoryPayload:
    name: str
    slug: str
    description: str
    icon: str
    sort_order: int


def build_category_payload(
    *,
    name: str,
    slug: str,
    description: str,
    icon: str,
    sort_order: int,
) -> CategoryPayload:
    name = name.strip()
    if not name:
        raise QuizError("com_quiz.error.name_required")
    slug = slug.strip() or _slugify(name)
    if not slug:
        raise QuizError("com_quiz.error.slug_required")
    if not re.match(r"^[a-z0-9-]+$", slug):
        raise QuizError("com_quiz.error.slug_invalid")
    return CategoryPayload(
        name=name,
        slug=slug,
        description=description.strip(),
        icon=icon.strip(),
        sort_order=sort_order,
    )


async def create_category(db: AsyncSession, payload: CategoryPayload) -> QuizCategory:
    existing = await get_category_by_slug(db, payload.slug)
    if existing:
        raise QuizError("com_quiz.error.slug_exists", slug=payload.slug)
    cat = QuizCategory(
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        icon=payload.icon,
        sort_order=payload.sort_order,
    )
    db.add(cat)
    await db.flush()
    await db.refresh(cat)
    return cat


async def update_category(db: AsyncSession, cat: QuizCategory, payload: CategoryPayload) -> None:
    if payload.slug != cat.slug:
        existing = await get_category_by_slug(db, payload.slug)
        if existing:
            raise QuizError("com_quiz.error.slug_exists", slug=payload.slug)
    cat.name = payload.name
    cat.slug = payload.slug
    cat.description = payload.description
    cat.icon = payload.icon
    cat.sort_order = payload.sort_order
    cat.updated_at = _now()
    await db.flush()


async def delete_category(db: AsyncSession, category_id: int) -> None:
    cat = await db.get(QuizCategory, category_id)
    if cat:
        await db.delete(cat)
        await db.flush()


# ---------------------------------------------------------------------------
# Question
# ---------------------------------------------------------------------------

async def list_questions(db: AsyncSession, category_id: int | None = None) -> list[QuizQuestion]:
    q = select(QuizQuestion).order_by(QuizQuestion.category_id, QuizQuestion.sort_order, QuizQuestion.id)
    if category_id is not None:
        q = q.where(QuizQuestion.category_id == category_id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_question(db: AsyncSession, question_id: int) -> QuizQuestion | None:
    return await db.get(QuizQuestion, question_id)


async def get_answers_for_question(db: AsyncSession, question_id: int) -> list[QuizAnswer]:
    result = await db.execute(
        select(QuizAnswer)
        .where(QuizAnswer.question_id == question_id)
        .order_by(QuizAnswer.sort_order, QuizAnswer.id)
    )
    return list(result.scalars().all())


async def get_answers_for_questions(db: AsyncSession, question_ids: list[int]) -> dict[int, list[QuizAnswer]]:
    if not question_ids:
        return {}
    result = await db.execute(
        select(QuizAnswer)
        .where(QuizAnswer.question_id.in_(question_ids))
        .order_by(QuizAnswer.question_id, QuizAnswer.sort_order)
    )
    out: dict[int, list[QuizAnswer]] = {}
    for ans in result.scalars().all():
        out.setdefault(ans.question_id, []).append(ans)
    return out


@dataclass(frozen=True)
class AnswerPayload:
    text: str
    is_correct: bool


@dataclass(frozen=True)
class QuestionPayload:
    category_id: int
    text: str
    explanation: str
    sort_order: int
    answers: list[AnswerPayload]


def build_question_payload(
    *,
    category_id: int,
    text: str,
    explanation: str,
    sort_order: int,
    answer_texts: list[str],
    correct_index: int,
) -> QuestionPayload:
    text = text.strip()
    if not text:
        raise QuizError("com_quiz.error.question_text_required")
    non_empty = [t.strip() for t in answer_texts if t.strip()]
    if len(non_empty) < 2:
        raise QuizError("com_quiz.error.answers_required")
    if correct_index < 0 or correct_index >= len(non_empty):
        raise QuizError("com_quiz.error.correct_required")
    answers = [
        AnswerPayload(text=t, is_correct=(i == correct_index))
        for i, t in enumerate(non_empty)
    ]
    return QuestionPayload(
        category_id=category_id,
        text=text,
        explanation=explanation.strip(),
        sort_order=sort_order,
        answers=answers,
    )


async def create_question(db: AsyncSession, payload: QuestionPayload) -> QuizQuestion:
    question = QuizQuestion(
        category_id=payload.category_id,
        text=payload.text,
        explanation=payload.explanation,
        sort_order=payload.sort_order,
    )
    db.add(question)
    await db.flush()
    for i, ans in enumerate(payload.answers):
        db.add(QuizAnswer(
            question_id=question.id,
            text=ans.text,
            is_correct=ans.is_correct,
            sort_order=i,
        ))
    await db.flush()
    await db.refresh(question)
    return question


async def update_question(db: AsyncSession, question: QuizQuestion, payload: QuestionPayload) -> None:
    question.category_id = payload.category_id
    question.text = payload.text
    question.explanation = payload.explanation
    question.sort_order = payload.sort_order
    question.updated_at = _now()
    await db.execute(delete(QuizAnswer).where(QuizAnswer.question_id == question.id))
    for i, ans in enumerate(payload.answers):
        db.add(QuizAnswer(
            question_id=question.id,
            text=ans.text,
            is_correct=ans.is_correct,
            sort_order=i,
        ))
    await db.flush()


async def delete_question(db: AsyncSession, question_id: int) -> None:
    q = await db.get(QuizQuestion, question_id)
    if q:
        await db.execute(delete(QuizAnswer).where(QuizAnswer.question_id == question_id))
        await db.delete(q)
        await db.flush()


async def count_questions_by_category(db: AsyncSession) -> dict[int, int]:
    result = await db.execute(
        select(QuizQuestion.category_id, func.count(QuizQuestion.id))
        .group_by(QuizQuestion.category_id)
    )
    return {row[0]: row[1] for row in result.all()}


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

async def list_tests(db: AsyncSession) -> list[QuizTest]:
    result = await db.execute(select(QuizTest).order_by(QuizTest.sort_order, QuizTest.title))
    return list(result.scalars().all())


async def list_published_tests(db: AsyncSession) -> list[QuizTest]:
    result = await db.execute(
        select(QuizTest)
        .where(QuizTest.status == "published")
        .order_by(QuizTest.sort_order, QuizTest.title)
    )
    return list(result.scalars().all())


async def get_test(db: AsyncSession, test_id: int) -> QuizTest | None:
    return await db.get(QuizTest, test_id)


async def get_test_by_slug(db: AsyncSession, slug: str) -> QuizTest | None:
    result = await db.execute(select(QuizTest).where(QuizTest.slug == slug))
    return result.scalar_one_or_none()


@dataclass(frozen=True)
class TestPayload:
    category_id: int
    title: str
    slug: str
    description: str
    status: str
    question_count: int
    passing_score: int
    time_limit: int | None
    shuffle_questions: bool
    shuffle_answers: bool
    show_correct_answers: bool
    sort_order: int


def build_test_payload(
    *,
    category_id: int,
    title: str,
    slug: str,
    description: str,
    status: str,
    question_count: int,
    passing_score: int,
    time_limit: int | None,
    shuffle_questions: bool,
    shuffle_answers: bool,
    show_correct_answers: bool,
    sort_order: int,
) -> TestPayload:
    title = title.strip()
    if not title:
        raise QuizError("com_quiz.error.title_required")
    slug = slug.strip() or _slugify(title)
    if not slug:
        raise QuizError("com_quiz.error.slug_required")
    if not re.match(r"^[a-z0-9-]+$", slug):
        raise QuizError("com_quiz.error.slug_invalid")
    if status not in ("draft", "published"):
        status = "draft"
    question_count = max(1, question_count)
    passing_score = max(0, min(100, passing_score))
    return TestPayload(
        category_id=category_id,
        title=title,
        slug=slug,
        description=description.strip(),
        status=status,
        question_count=question_count,
        passing_score=passing_score,
        time_limit=time_limit,
        shuffle_questions=shuffle_questions,
        shuffle_answers=shuffle_answers,
        show_correct_answers=show_correct_answers,
        sort_order=sort_order,
    )


async def create_test(db: AsyncSession, payload: TestPayload) -> QuizTest:
    existing = await get_test_by_slug(db, payload.slug)
    if existing:
        raise QuizError("com_quiz.error.slug_exists", slug=payload.slug)
    test = QuizTest(
        category_id=payload.category_id,
        title=payload.title,
        slug=payload.slug,
        description=payload.description,
        status=payload.status,
        question_count=payload.question_count,
        passing_score=payload.passing_score,
        time_limit=payload.time_limit,
        shuffle_questions=payload.shuffle_questions,
        shuffle_answers=payload.shuffle_answers,
        show_correct_answers=payload.show_correct_answers,
        sort_order=payload.sort_order,
    )
    db.add(test)
    await db.flush()
    await db.refresh(test)
    return test


async def update_test(db: AsyncSession, test: QuizTest, payload: TestPayload) -> None:
    if payload.slug != test.slug:
        existing = await get_test_by_slug(db, payload.slug)
        if existing:
            raise QuizError("com_quiz.error.slug_exists", slug=payload.slug)
    test.category_id = payload.category_id
    test.title = payload.title
    test.slug = payload.slug
    test.description = payload.description
    test.status = payload.status
    test.question_count = payload.question_count
    test.passing_score = payload.passing_score
    test.time_limit = payload.time_limit
    test.shuffle_questions = payload.shuffle_questions
    test.shuffle_answers = payload.shuffle_answers
    test.show_correct_answers = payload.show_correct_answers
    test.sort_order = payload.sort_order
    test.updated_at = _now()
    await db.flush()


async def delete_test(db: AsyncSession, test_id: int) -> None:
    t = await db.get(QuizTest, test_id)
    if t:
        await db.delete(t)
        await db.flush()


# ---------------------------------------------------------------------------
# Attempt
# ---------------------------------------------------------------------------

async def start_attempt(db: AsyncSession, test: QuizTest) -> QuizAttempt:
    questions = await list_questions(db, category_id=test.category_id)
    if not questions:
        raise QuizError("com_quiz.error.no_questions")
    count = min(test.question_count, len(questions))
    if test.shuffle_questions:
        selected = random.sample(questions, count)
    else:
        selected = sorted(questions, key=lambda q: (q.sort_order, q.id))[:count]
    attempt = QuizAttempt(
        id=str(uuid.uuid4()),
        test_id=test.id,
        session_token=str(uuid.uuid4()),
        question_ids=[q.id for q in selected],
    )
    db.add(attempt)
    await db.flush()
    await db.refresh(attempt)
    return attempt


async def get_attempt_by_token(db: AsyncSession, token: str) -> QuizAttempt | None:
    result = await db.execute(
        select(QuizAttempt).where(QuizAttempt.session_token == token)
    )
    return result.scalar_one_or_none()


async def get_attempt(db: AsyncSession, attempt_id: str) -> QuizAttempt | None:
    return await db.get(QuizAttempt, attempt_id)


async def save_answer(
    db: AsyncSession,
    attempt: QuizAttempt,
    question_id: int,
    answer_id: int | None,
) -> None:
    existing = await db.execute(
        select(QuizAttemptAnswer).where(
            QuizAttemptAnswer.attempt_id == attempt.id,
            QuizAttemptAnswer.question_id == question_id,
        )
    )
    row = existing.scalar_one_or_none()

    is_correct = False
    if answer_id is not None:
        ans = await db.get(QuizAnswer, answer_id)
        is_correct = bool(ans and ans.is_correct)

    if row:
        row.answer_id = answer_id
        row.is_correct = is_correct
    else:
        db.add(QuizAttemptAnswer(
            attempt_id=attempt.id,
            question_id=question_id,
            answer_id=answer_id,
            is_correct=is_correct,
        ))
    await db.flush()


async def finish_attempt(db: AsyncSession, attempt: QuizAttempt, test: QuizTest) -> None:
    if attempt.finished_at is not None:
        return
    answers_result = await db.execute(
        select(QuizAttemptAnswer).where(QuizAttemptAnswer.attempt_id == attempt.id)
    )
    answers = list(answers_result.scalars().all())
    total = len(attempt.question_ids)
    correct = sum(1 for a in answers if a.is_correct)
    score = round(correct / total * 100) if total > 0 else 0
    attempt.score = score
    attempt.passed = score >= test.passing_score
    attempt.finished_at = _now()
    await db.flush()


async def get_attempt_detail(
    db: AsyncSession,
    attempt: QuizAttempt,
) -> list[dict]:
    question_ids = attempt.question_ids
    if not question_ids:
        return []

    qs_result = await db.execute(
        select(QuizQuestion).where(QuizQuestion.id.in_(question_ids))
    )
    questions_map = {q.id: q for q in qs_result.scalars().all()}

    answers_map = await get_answers_for_questions(db, question_ids)

    attempt_answers_result = await db.execute(
        select(QuizAttemptAnswer).where(QuizAttemptAnswer.attempt_id == attempt.id)
    )
    attempt_answers = {aa.question_id: aa for aa in attempt_answers_result.scalars().all()}

    rows = []
    for qid in question_ids:
        q = questions_map.get(qid)
        if not q:
            continue
        aa = attempt_answers.get(qid)
        all_answers = answers_map.get(qid, [])
        correct_answer = next((a for a in all_answers if a.is_correct), None)
        chosen_answer = None
        if aa and aa.answer_id:
            chosen_answer = next((a for a in all_answers if a.id == aa.answer_id), None)
        rows.append({
            "question": q,
            "answers": all_answers,
            "chosen": chosen_answer,
            "correct_answer": correct_answer,
            "is_correct": bool(aa and aa.is_correct),
        })
    return rows


async def list_attempts(db: AsyncSession, limit: int = 100) -> list[QuizAttempt]:
    result = await db.execute(
        select(QuizAttempt)
        .where(QuizAttempt.finished_at.isnot(None))
        .order_by(QuizAttempt.finished_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def count_attempts_by_test(db: AsyncSession) -> dict[int, int]:
    result = await db.execute(
        select(QuizAttempt.test_id, func.count(QuizAttempt.id))
        .where(QuizAttempt.finished_at.isnot(None))
        .group_by(QuizAttempt.test_id)
    )
    return {row[0]: row[1] for row in result.all()}
