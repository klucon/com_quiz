from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.admin.deps import CurrentAdminUser
from src.api.admin.render import admin_render
from src.core.acl import require_admin_permission
from src.core.system_settings import get_runtime_settings
from src.core.templates import make_t
from src.database.base import get_db_session

from .service import (
    QuizError,
    build_category_payload,
    build_question_payload,
    build_test_payload,
    count_attempts_by_test,
    count_questions_by_category,
    create_category,
    create_question,
    create_test,
    delete_category,
    delete_question,
    delete_test,
    get_answers_for_question,
    get_category,
    get_question,
    get_test,
    list_attempts,
    list_categories,
    list_questions,
    list_tests,
    update_category,
    update_question,
    update_test,
)

router = APIRouter(
    prefix="/admin/com_quiz",
    tags=["com_quiz"],
    dependencies=[Depends(require_admin_permission("quiz.manage"))],
)


async def _ct(db: AsyncSession):
    runtime = await get_runtime_settings(db)
    return make_t(runtime.locale, "com_quiz")


def _flash(request: Request, flash_type: str, text: str) -> None:
    request.session["flash"] = {"type": flash_type, "text": text}


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "on", "yes"}


# ---------------------------------------------------------------------------
# Index – overview
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
async def index(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    tests = await list_tests(db)
    categories = await list_categories(db)
    q_counts = await count_questions_by_category(db)
    a_counts = await count_attempts_by_test(db)
    flash = request.session.pop("flash", None)
    return await admin_render(
        "admin/com_quiz/index.html",
        request=request, db=db, user=user, ct=await _ct(db),
        tests=tests, categories=categories,
        question_counts=q_counts, attempt_counts=a_counts,
        flash=flash,
    )


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

@router.get("/categories", response_class=HTMLResponse)
async def categories_index(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    cats = await list_categories(db)
    q_counts = await count_questions_by_category(db)
    flash = request.session.pop("flash", None)
    return await admin_render(
        "admin/com_quiz/categories/index.html",
        request=request, db=db, user=user, ct=await _ct(db),
        categories=cats, question_counts=q_counts, flash=flash,
    )


@router.get("/categories/new", response_class=HTMLResponse)
async def categories_new(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    flash = request.session.pop("flash", None)
    return await admin_render(
        "admin/com_quiz/categories/form.html",
        request=request, db=db, user=user, ct=await _ct(db),
        category=None, flash=flash,
    )


@router.post("/categories/new")
async def categories_new_submit(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    form = await request.form()
    try:
        payload = build_category_payload(
            name=str(form.get("name", "")),
            slug=str(form.get("slug", "")),
            description=str(form.get("description", "")),
            icon=str(form.get("icon", "")),
            sort_order=int(str(form.get("sort_order", "0")) or "0"),
        )
        await create_category(db, payload)
        await db.commit()
    except (QuizError, ValueError) as exc:
        await db.rollback()
        key = exc.key if isinstance(exc, QuizError) else "com_quiz.error.invalid_input"
        kwargs = exc.kwargs if isinstance(exc, QuizError) else {}
        _flash(request, "danger", ct(key, **kwargs))
        return RedirectResponse("/admin/com_quiz/categories/new", status_code=303)
    _flash(request, "success", ct("com_quiz.success.category_created"))
    return RedirectResponse("/admin/com_quiz/categories", status_code=303)


@router.get("/categories/{cat_id}/edit", response_class=HTMLResponse)
async def categories_edit(
    cat_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    cat = await get_category(db, cat_id)
    if cat is None:
        return RedirectResponse("/admin/com_quiz/categories", status_code=303)
    flash = request.session.pop("flash", None)
    return await admin_render(
        "admin/com_quiz/categories/form.html",
        request=request, db=db, user=user, ct=await _ct(db),
        category=cat, flash=flash,
    )


@router.post("/categories/{cat_id}/edit")
async def categories_edit_submit(
    cat_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    cat = await get_category(db, cat_id)
    if cat is None:
        return RedirectResponse("/admin/com_quiz/categories", status_code=303)
    ct = await _ct(db)
    form = await request.form()
    try:
        payload = build_category_payload(
            name=str(form.get("name", cat.name)),
            slug=str(form.get("slug", cat.slug)),
            description=str(form.get("description", cat.description)),
            icon=str(form.get("icon", cat.icon)),
            sort_order=int(str(form.get("sort_order", str(cat.sort_order))) or "0"),
        )
        await update_category(db, cat, payload)
        await db.commit()
    except (QuizError, ValueError) as exc:
        await db.rollback()
        key = exc.key if isinstance(exc, QuizError) else "com_quiz.error.invalid_input"
        kwargs = exc.kwargs if isinstance(exc, QuizError) else {}
        _flash(request, "danger", ct(key, **kwargs))
        return RedirectResponse(f"/admin/com_quiz/categories/{cat_id}/edit", status_code=303)
    _flash(request, "success", ct("com_quiz.success.category_updated"))
    return RedirectResponse("/admin/com_quiz/categories", status_code=303)


@router.post("/categories/{cat_id}/delete")
async def categories_delete(
    cat_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await delete_category(db, cat_id)
    await db.commit()
    ct = await _ct(db)
    _flash(request, "success", ct("com_quiz.success.category_deleted"))
    return RedirectResponse("/admin/com_quiz/categories", status_code=303)


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

@router.get("/questions", response_class=HTMLResponse)
async def questions_index(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
    category: int | None = None,
) -> HTMLResponse:
    questions = await list_questions(db, category_id=category)
    categories = await list_categories(db)
    flash = request.session.pop("flash", None)
    return await admin_render(
        "admin/com_quiz/questions/index.html",
        request=request, db=db, user=user, ct=await _ct(db),
        questions=questions, categories=categories,
        selected_category=category, flash=flash,
    )


@router.get("/questions/new", response_class=HTMLResponse)
async def questions_new(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    categories = await list_categories(db)
    flash = request.session.pop("flash", None)
    return await admin_render(
        "admin/com_quiz/questions/form.html",
        request=request, db=db, user=user, ct=await _ct(db),
        question=None, answers=[], categories=categories, flash=flash,
    )


@router.post("/questions/new")
async def questions_new_submit(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    form = await request.form()
    answer_texts = [str(form.get(f"answer_text_{i}", "")) for i in range(8)]
    correct_raw = str(form.get("answer_correct", "0"))
    try:
        correct_index = int(correct_raw)
        payload = build_question_payload(
            category_id=int(str(form.get("category_id", "0"))),
            text=str(form.get("text", "")),
            explanation=str(form.get("explanation", "")),
            sort_order=int(str(form.get("sort_order", "0")) or "0"),
            answer_texts=answer_texts,
            correct_index=correct_index,
        )
        await create_question(db, payload)
        await db.commit()
    except (QuizError, ValueError) as exc:
        await db.rollback()
        key = exc.key if isinstance(exc, QuizError) else "com_quiz.error.invalid_input"
        kwargs = exc.kwargs if isinstance(exc, QuizError) else {}
        _flash(request, "danger", ct(key, **kwargs))
        return RedirectResponse("/admin/com_quiz/questions/new", status_code=303)
    _flash(request, "success", ct("com_quiz.success.question_created"))
    return RedirectResponse("/admin/com_quiz/questions", status_code=303)


@router.get("/questions/{q_id}/edit", response_class=HTMLResponse)
async def questions_edit(
    q_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    question = await get_question(db, q_id)
    if question is None:
        return RedirectResponse("/admin/com_quiz/questions", status_code=303)
    answers = await get_answers_for_question(db, q_id)
    categories = await list_categories(db)
    flash = request.session.pop("flash", None)
    return await admin_render(
        "admin/com_quiz/questions/form.html",
        request=request, db=db, user=user, ct=await _ct(db),
        question=question, answers=answers, categories=categories, flash=flash,
    )


@router.post("/questions/{q_id}/edit")
async def questions_edit_submit(
    q_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    question = await get_question(db, q_id)
    if question is None:
        return RedirectResponse("/admin/com_quiz/questions", status_code=303)
    ct = await _ct(db)
    form = await request.form()
    answer_texts = [str(form.get(f"answer_text_{i}", "")) for i in range(8)]
    correct_raw = str(form.get("answer_correct", "0"))
    try:
        correct_index = int(correct_raw)
        payload = build_question_payload(
            category_id=int(str(form.get("category_id", str(question.category_id)))),
            text=str(form.get("text", question.text)),
            explanation=str(form.get("explanation", question.explanation)),
            sort_order=int(str(form.get("sort_order", str(question.sort_order))) or "0"),
            answer_texts=answer_texts,
            correct_index=correct_index,
        )
        await update_question(db, question, payload)
        await db.commit()
    except (QuizError, ValueError) as exc:
        await db.rollback()
        key = exc.key if isinstance(exc, QuizError) else "com_quiz.error.invalid_input"
        kwargs = exc.kwargs if isinstance(exc, QuizError) else {}
        _flash(request, "danger", ct(key, **kwargs))
        return RedirectResponse(f"/admin/com_quiz/questions/{q_id}/edit", status_code=303)
    _flash(request, "success", ct("com_quiz.success.question_updated"))
    return RedirectResponse("/admin/com_quiz/questions", status_code=303)


@router.post("/questions/{q_id}/delete")
async def questions_delete(
    q_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await delete_question(db, q_id)
    await db.commit()
    ct = await _ct(db)
    _flash(request, "success", ct("com_quiz.success.question_deleted"))
    return RedirectResponse("/admin/com_quiz/questions", status_code=303)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@router.get("/tests", response_class=HTMLResponse)
async def tests_index(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    tests = await list_tests(db)
    categories = await list_categories(db)
    a_counts = await count_attempts_by_test(db)
    flash = request.session.pop("flash", None)
    return await admin_render(
        "admin/com_quiz/tests/index.html",
        request=request, db=db, user=user, ct=await _ct(db),
        tests=tests, categories=categories, attempt_counts=a_counts, flash=flash,
    )


@router.get("/tests/new", response_class=HTMLResponse)
async def tests_new(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    categories = await list_categories(db)
    flash = request.session.pop("flash", None)
    return await admin_render(
        "admin/com_quiz/tests/form.html",
        request=request, db=db, user=user, ct=await _ct(db),
        test=None, categories=categories, flash=flash,
    )


@router.post("/tests/new")
async def tests_new_submit(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    form = await request.form()
    try:
        tl_raw = str(form.get("time_limit", "")).strip()
        payload = build_test_payload(
            category_id=int(str(form.get("category_id", "0"))),
            title=str(form.get("title", "")),
            slug=str(form.get("slug", "")),
            description=str(form.get("description", "")),
            status=str(form.get("status", "draft")),
            question_count=int(str(form.get("question_count", "20")) or "20"),
            passing_score=int(str(form.get("passing_score", "70")) or "70"),
            time_limit=int(tl_raw) if tl_raw else None,
            shuffle_questions=_parse_bool(str(form.get("shuffle_questions", "0"))),
            shuffle_answers=_parse_bool(str(form.get("shuffle_answers", "0"))),
            show_correct_answers=_parse_bool(str(form.get("show_correct_answers", "1"))),
            sort_order=int(str(form.get("sort_order", "0")) or "0"),
        )
        await create_test(db, payload)
        await db.commit()
    except (QuizError, ValueError) as exc:
        await db.rollback()
        key = exc.key if isinstance(exc, QuizError) else "com_quiz.error.invalid_input"
        kwargs = exc.kwargs if isinstance(exc, QuizError) else {}
        _flash(request, "danger", ct(key, **kwargs))
        return RedirectResponse("/admin/com_quiz/tests/new", status_code=303)
    _flash(request, "success", ct("com_quiz.success.test_created"))
    return RedirectResponse("/admin/com_quiz/tests", status_code=303)


@router.get("/tests/{test_id}/edit", response_class=HTMLResponse)
async def tests_edit(
    test_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    test = await get_test(db, test_id)
    if test is None:
        return RedirectResponse("/admin/com_quiz/tests", status_code=303)
    categories = await list_categories(db)
    flash = request.session.pop("flash", None)
    return await admin_render(
        "admin/com_quiz/tests/form.html",
        request=request, db=db, user=user, ct=await _ct(db),
        test=test, categories=categories, flash=flash,
    )


@router.post("/tests/{test_id}/edit")
async def tests_edit_submit(
    test_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    test = await get_test(db, test_id)
    if test is None:
        return RedirectResponse("/admin/com_quiz/tests", status_code=303)
    ct = await _ct(db)
    form = await request.form()
    try:
        tl_raw = str(form.get("time_limit", "")).strip()
        payload = build_test_payload(
            category_id=int(str(form.get("category_id", str(test.category_id)))),
            title=str(form.get("title", test.title)),
            slug=str(form.get("slug", test.slug)),
            description=str(form.get("description", test.description)),
            status=str(form.get("status", test.status)),
            question_count=int(str(form.get("question_count", str(test.question_count))) or "20"),
            passing_score=int(str(form.get("passing_score", str(test.passing_score))) or "70"),
            time_limit=int(tl_raw) if tl_raw else None,
            shuffle_questions=_parse_bool(str(form.get("shuffle_questions", "0"))),
            shuffle_answers=_parse_bool(str(form.get("shuffle_answers", "0"))),
            show_correct_answers=_parse_bool(str(form.get("show_correct_answers", "1"))),
            sort_order=int(str(form.get("sort_order", str(test.sort_order))) or "0"),
        )
        await update_test(db, test, payload)
        await db.commit()
    except (QuizError, ValueError) as exc:
        await db.rollback()
        key = exc.key if isinstance(exc, QuizError) else "com_quiz.error.invalid_input"
        kwargs = exc.kwargs if isinstance(exc, QuizError) else {}
        _flash(request, "danger", ct(key, **kwargs))
        return RedirectResponse(f"/admin/com_quiz/tests/{test_id}/edit", status_code=303)
    _flash(request, "success", ct("com_quiz.success.test_updated"))
    return RedirectResponse("/admin/com_quiz/tests", status_code=303)


@router.post("/tests/{test_id}/delete")
async def tests_delete(
    test_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await delete_test(db, test_id)
    await db.commit()
    ct = await _ct(db)
    _flash(request, "success", ct("com_quiz.success.test_deleted"))
    return RedirectResponse("/admin/com_quiz/tests", status_code=303)


# ---------------------------------------------------------------------------
# Attempts
# ---------------------------------------------------------------------------

@router.get("/attempts", response_class=HTMLResponse)
async def attempts_index(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    attempts = await list_attempts(db)
    tests = await list_tests(db)
    tests_map = {t.id: t for t in tests}
    flash = request.session.pop("flash", None)
    return await admin_render(
        "admin/com_quiz/attempts/index.html",
        request=request, db=db, user=user, ct=await _ct(db),
        attempts=attempts, tests_map=tests_map, flash=flash,
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@router.get("/settings", response_class=HTMLResponse)
async def settings_form(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    flash = request.session.pop("flash", None)
    return await admin_render(
        "admin/com_quiz/settings.html",
        request=request, db=db, user=user, ct=await _ct(db),
        flash=flash,
    )


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

@router.get("/import", response_class=HTMLResponse)
async def import_form(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    flash = request.session.pop("flash", None)
    return await admin_render(
        "admin/com_quiz/import.html",
        request=request, db=db, user=user, ct=await _ct(db),
        flash=flash,
    )


@router.post("/import")
async def import_submit(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
    file: UploadFile = File(...),
) -> Response:
    ct = await _ct(db)
    try:
        content = await file.read()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        from .importer import import_from_json
        stats = await import_from_json(db, tmp_path)
        tmp_path.unlink(missing_ok=True)
        flash_type = "success" if stats["created"] > 0 else "warning"
        msg = ct("com_quiz.success.imported",
                 created=stats["created"], errors=stats["errors"])
        if stats.get("first_error"):
            msg += f"<br><small class='font-monospace'>{stats['first_error']}</small>"
        _flash(request, flash_type, msg)
    except Exception as exc:
        _flash(request, "danger", str(exc))
    return RedirectResponse("/admin/com_quiz/import", status_code=303)


@router.post("/settings")
async def settings_submit(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    _flash(request, "success", ct("com_quiz.settings.saved"))
    return RedirectResponse("/admin/com_quiz/settings", status_code=303)
