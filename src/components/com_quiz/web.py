from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.system_settings import get_runtime_settings
from src.core.templates import make_t
from src.database.base import get_db_session

try:
    from src.core.web_render import web_render
except ImportError:
    from src.api.web.render import web_render  # type: ignore[no-redef]

from .service import (
    QuizError,
    finish_attempt,
    get_attempt_by_token,
    get_attempt_detail,
    get_test_by_slug,
    list_published_tests,
    save_answer,
    start_attempt,
)

router = APIRouter(prefix="/quiz", tags=["com_quiz_web"])


async def _ct(db: AsyncSession, locale: str):
    return make_t(locale, "com_quiz")


async def _locale(db: AsyncSession) -> str:
    runtime = await get_runtime_settings(db)
    return runtime.locale


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_locale_from_request(request: Request) -> str:
    return getattr(request.state, "locale", "cs_CZ")


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "on", "yes"}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
async def quiz_index(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    locale = _get_locale_from_request(request)
    tests = await list_published_tests(db)
    ct = await _ct(db, locale)
    return await web_render(
        "com_quiz/index.html",
        request=request, db=db, locale=locale, ct=ct,
        tests=tests,
    )


@router.get("/{slug}", response_class=HTMLResponse)
async def quiz_intro(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    locale = _get_locale_from_request(request)
    test = await get_test_by_slug(db, slug)
    if test is None or test.status != "published":
        return RedirectResponse("/quiz", status_code=302)
    ct = await _ct(db, locale)
    return await web_render(
        "com_quiz/intro.html",
        request=request, db=db, locale=locale, ct=ct,
        test=test,
    )


@router.post("/{slug}/start")
async def quiz_start(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    test = await get_test_by_slug(db, slug)
    if test is None or test.status != "published":
        return RedirectResponse("/quiz", status_code=303)
    try:
        attempt = await start_attempt(db, test)
        await db.commit()
    except QuizError:
        return RedirectResponse(f"/quiz/{slug}", status_code=303)
    return RedirectResponse(
        f"/quiz/{slug}/q/1?token={attempt.session_token}",
        status_code=303,
    )


@router.get("/{slug}/q/{n}", response_class=HTMLResponse)
async def quiz_question(
    slug: str,
    n: int,
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    locale = _get_locale_from_request(request)
    test = await get_test_by_slug(db, slug)
    attempt = await get_attempt_by_token(db, token)
    if test is None or attempt is None or attempt.test_id != test.id:
        return RedirectResponse(f"/quiz/{slug}", status_code=302)
    if attempt.finished_at is not None:
        return RedirectResponse(f"/quiz/{slug}/result?token={token}", status_code=302)

    question_ids = attempt.question_ids
    total = len(question_ids)
    if n < 1 or n > total:
        return RedirectResponse(f"/quiz/{slug}/result?token={token}", status_code=302)

    from .service import get_question, get_answers_for_question
    question_id = question_ids[n - 1]
    question = await get_question(db, question_id)
    if question is None:
        return RedirectResponse(f"/quiz/{slug}/result?token={token}", status_code=302)

    answers = await get_answers_for_question(db, question_id)
    if test.shuffle_answers:
        import random
        answers = list(answers)
        random.shuffle(answers)

    ct = await _ct(db, locale)
    return await web_render(
        "com_quiz/question.html",
        request=request, db=db, locale=locale, ct=ct,
        test=test, question=question, answers=answers,
        n=n, total=total, token=token,
        time_limit=test.time_limit,
    )


@router.post("/{slug}/q/{n}")
async def quiz_question_submit(
    slug: str,
    n: int,
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    test = await get_test_by_slug(db, slug)
    attempt = await get_attempt_by_token(db, token)
    if test is None or attempt is None or attempt.test_id != test.id:
        return RedirectResponse(f"/quiz/{slug}", status_code=303)
    if attempt.finished_at is not None:
        return RedirectResponse(f"/quiz/{slug}/result?token={token}", status_code=303)

    question_ids = attempt.question_ids
    total = len(question_ids)
    if n < 1 or n > total:
        return RedirectResponse(f"/quiz/{slug}/result?token={token}", status_code=303)

    form = await request.form()
    answer_id_raw = str(form.get("answer_id", "")).strip()
    answer_id = int(answer_id_raw) if answer_id_raw.isdigit() else None

    question_id = question_ids[n - 1]
    await save_answer(db, attempt, question_id, answer_id)

    if n >= total:
        await finish_attempt(db, attempt, test)
        await db.commit()
        return RedirectResponse(f"/quiz/{slug}/result?token={token}", status_code=303)

    await db.commit()
    return RedirectResponse(f"/quiz/{slug}/q/{n + 1}?token={token}", status_code=303)


@router.get("/{slug}/result", response_class=HTMLResponse)
async def quiz_result(
    slug: str,
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    locale = _get_locale_from_request(request)
    test = await get_test_by_slug(db, slug)
    attempt = await get_attempt_by_token(db, token)
    if test is None or attempt is None or attempt.test_id != test.id:
        return RedirectResponse(f"/quiz/{slug}", status_code=302)
    if attempt.finished_at is None:
        return RedirectResponse(f"/quiz/{slug}", status_code=302)

    detail = await get_attempt_detail(db, attempt)
    ct = await _ct(db, locale)
    return await web_render(
        "com_quiz/result.html",
        request=request, db=db, locale=locale, ct=ct,
        test=test, attempt=attempt, detail=detail,
    )


@router.get("/{slug}/pdf")
async def quiz_pdf(
    slug: str,
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    test = await get_test_by_slug(db, slug)
    attempt = await get_attempt_by_token(db, token)
    if test is None or attempt is None or attempt.test_id != test.id or attempt.finished_at is None:
        return RedirectResponse(f"/quiz/{slug}", status_code=302)

    detail = await get_attempt_detail(db, attempt)
    correct = sum(1 for row in detail if row["is_correct"])
    total = len(detail)
    score = attempt.score or 0

    date_str = attempt.finished_at.strftime("%d.%m.%Y %H:%M") if attempt.finished_at else ""

    from .pdf import generate_pdf_bytes
    pdf_bytes = generate_pdf_bytes(
        test_title=test.title,
        date=date_str,
        total=total,
        correct=correct,
        score=score,
        passing_score=test.passing_score,
        passed=bool(attempt.passed),
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
        detail_rows=detail,
        show_correct_answers=test.show_correct_answers,
    )

    filename = f"test-{slug}-{token[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
