from __future__ import annotations

from datetime import datetime


_TEMPLATE = """<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8"/>
<style>
  body {{ font-family: DejaVu Sans, sans-serif; font-size: 11pt; color: #222; margin: 20mm; }}
  h1 {{ font-size: 16pt; margin-bottom: 4px; }}
  .meta {{ color: #555; font-size: 9pt; margin-bottom: 16px; }}
  .summary {{ border: 1px solid #ccc; border-radius: 4px; padding: 12px 16px; margin-bottom: 20px; background: #f8f8f8; }}
  .summary .score {{ font-size: 22pt; font-weight: bold; }}
  .summary .result-pass {{ color: #1a7a3c; }}
  .summary .result-fail {{ color: #c0392b; }}
  .question {{ margin-bottom: 16px; border-top: 1px solid #ddd; padding-top: 10px; }}
  .q-text {{ font-weight: bold; margin-bottom: 6px; }}
  .q-num {{ color: #888; font-size: 9pt; }}
  .answer-row {{ margin: 2px 0; padding: 2px 6px; font-size: 10pt; border-radius: 3px; }}
  .answer-chosen-correct {{ background: #d4edda; }}
  .answer-chosen-wrong {{ background: #f8d7da; }}
  .answer-correct-missed {{ background: #fff3cd; }}
  .tag {{ display: inline-block; border-radius: 3px; padding: 1px 6px; font-size: 8pt; font-weight: bold; margin-left: 6px; }}
  .tag-correct {{ background: #1a7a3c; color: #fff; }}
  .tag-wrong {{ background: #c0392b; color: #fff; }}
  .tag-missed {{ background: #856404; color: #fff; }}
  .explanation {{ font-size: 9pt; color: #555; margin-top: 4px; border-left: 3px solid #ccc; padding-left: 8px; }}
  footer {{ margin-top: 24px; font-size: 8pt; color: #aaa; text-align: center; }}
</style>
</head>
<body>
<h1>{test_title}</h1>
<div class="meta">
  Datum: {date} &nbsp;|&nbsp;
  Otázek: {total} &nbsp;|&nbsp;
  Správně: {correct} ({score}&nbsp;%)
  {time_info}
</div>

<div class="summary">
  <div class="score {result_class}">{score}&nbsp;% &mdash; {result_label}</div>
  <div style="font-size:9pt;color:#555;margin-top:4px;">
    Hranice úspěšnosti: {passing_score}&nbsp;%
  </div>
</div>

{questions_html}

<footer>Vygenerováno systémem KLUCON CMS &middot; {date}</footer>
</body>
</html>
"""

_QUESTION_TEMPLATE = """<div class="question">
  <div class="q-text"><span class="q-num">{num}.</span> {q_text}</div>
  {answers_html}
  {explanation_html}
</div>"""


def _render_answers(row: dict, show_correct: bool) -> str:
    lines = []
    for ans in row["answers"]:
        chosen = row["chosen"] and row["chosen"].id == ans.id
        css = ""
        tag = ""
        if chosen and ans.is_correct:
            css = "answer-chosen-correct"
            tag = '<span class="tag tag-correct">✓ správně</span>'
        elif chosen and not ans.is_correct:
            css = "answer-chosen-wrong"
            tag = '<span class="tag tag-wrong">✗ chyba</span>'
        elif not chosen and ans.is_correct and show_correct:
            css = "answer-correct-missed"
            tag = '<span class="tag tag-missed">správná odpověď</span>'
        bullet = "▶" if chosen else "○"
        lines.append(
            f'<div class="answer-row {css}">{bullet} {ans.text}{tag}</div>'
        )
    return "\n".join(lines)


def _render_explanation(row: dict, show_correct: bool) -> str:
    if not row["is_correct"] and row["question"].explanation and show_correct:
        text = row["question"].explanation.replace("\n", "<br/>")
        return f'<div class="explanation">{text}</div>'
    return ""


def generate_pdf_bytes(
    *,
    test_title: str,
    date: str,
    total: int,
    correct: int,
    score: int,
    passing_score: int,
    passed: bool,
    started_at: datetime | None,
    finished_at: datetime | None,
    detail_rows: list[dict],
    show_correct_answers: bool,
) -> bytes:
    try:
        from weasyprint import HTML  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "WeasyPrint is not installed. Install it with: pip install weasyprint"
        ) from exc

    time_info = ""
    if started_at and finished_at:
        delta = int((finished_at - started_at).total_seconds())
        mins, secs = divmod(delta, 60)
        time_info = f"&nbsp;|&nbsp; Čas: {mins}:{secs:02d}"

    result_class = "result-pass" if passed else "result-fail"
    result_label = "Úspěšně splněno" if passed else "Nesplněno"

    questions_html_parts = []
    for i, row in enumerate(detail_rows, 1):
        answers_html = _render_answers(row, show_correct_answers)
        explanation_html = _render_explanation(row, show_correct_answers)
        questions_html_parts.append(_QUESTION_TEMPLATE.format(
            num=i,
            q_text=row["question"].text,
            answers_html=answers_html,
            explanation_html=explanation_html,
        ))

    html = _TEMPLATE.format(
        test_title=test_title,
        date=date,
        total=total,
        correct=correct,
        score=score,
        passing_score=passing_score,
        result_class=result_class,
        result_label=result_label,
        time_info=time_info,
        questions_html="\n".join(questions_html_parts),
    )
    return HTML(string=html).write_pdf()
