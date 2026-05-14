"""Komponenta com_quiz – systém testů a kvízů."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.registry import ComponentRegistry

_COMPONENT_DIR = Path(__file__).parent
_manifest: dict = {}


def _load_manifest() -> dict:
    global _manifest
    if not _manifest:
        try:
            _manifest = json.loads((_COMPONENT_DIR / "manifest.json").read_text(encoding="utf-8"))
        except Exception:
            _manifest = {}
    return _manifest


def setup(reg: "ComponentRegistry") -> None:
    from src.components.com_quiz import admin, web
    from src.i18n.translator import translator

    manifest = _load_manifest()

    reg.register("com_quiz", "src.components.com_quiz")
    reg.register_display_name("com_quiz", manifest.get("display_name_key", "components.name.com_quiz"))
    reg.register_admin_url("com_quiz", manifest.get("admin_url", "/admin/com_quiz"))
    reg.register_router(admin.router)
    reg.register_router(web.router)

    translator.load_domain("com_quiz", _COMPONENT_DIR / "i18n")


async def uninstall_schema(engine: object) -> None:
    from src.components.com_quiz.models import (
        QuizAnswer,
        QuizAttemptAnswer,
        QuizAttempt,
        QuizQuestion,
        QuizTest,
        QuizCategory,
    )

    async with engine.begin() as conn:
        for table in [
            QuizAttemptAnswer.__table__,
            QuizAttempt.__table__,
            QuizAnswer.__table__,
            QuizQuestion.__table__,
            QuizTest.__table__,
            QuizCategory.__table__,
        ]:
            await conn.run_sync(lambda sync_conn, t=table: t.drop(sync_conn, checkfirst=True))
