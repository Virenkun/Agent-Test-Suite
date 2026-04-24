"""CSV + PDF exports for a single test run."""
import csv
import io
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.call import Call
from app.models.call_evaluation import CallEvaluation
from app.models.criterion import EvaluationCriterion
from app.models.test_case import TestCase
from app.models.test_run import TestRun


class ExportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_run(self, run_id: UUID) -> tuple[TestRun, TestCase]:
        result = await self.db.execute(
            select(TestRun)
            .options(selectinload(TestRun.calls).selectinload(Call.evaluations))
            .where(TestRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise NotFoundError(f"TestRun {run_id} not found")
        tc_res = await self.db.execute(
            select(TestCase)
            .options(selectinload(TestCase.criteria))
            .where(TestCase.id == run.test_case_id)
        )
        tc = tc_res.scalar_one()
        return run, tc

    async def export_csv(self, run_id: UUID) -> bytes:
        run, tc = await self._load_run(run_id)
        criteria_by_id: dict[UUID, EvaluationCriterion] = {
            c.id: c for c in tc.criteria
        }

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "run_id",
                "test_case",
                "call_id",
                "call_status",
                "duration_sec",
                "cost_usd",
                "criterion",
                "criterion_type",
                "passed",
                "score",
                "max_score",
                "confidence",
                "reasoning",
                "llm_cost_usd",
            ]
        )
        for call in run.calls:
            if not call.evaluations:
                writer.writerow(
                    [
                        str(run.id),
                        tc.name,
                        str(call.id),
                        call.status.value,
                        call.duration_sec,
                        str(call.cost_usd),
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                    ]
                )
                continue
            for ev in call.evaluations:
                crit = criteria_by_id.get(ev.criterion_id)
                writer.writerow(
                    [
                        str(run.id),
                        tc.name,
                        str(call.id),
                        call.status.value,
                        call.duration_sec,
                        str(call.cost_usd),
                        crit.name if crit else "",
                        crit.type.value if crit else "",
                        "" if ev.passed is None else str(ev.passed).lower(),
                        "" if ev.score is None else str(ev.score),
                        crit.max_score if crit and crit.max_score is not None else "",
                        "" if ev.confidence is None else str(ev.confidence),
                        (ev.reasoning or "").replace("\n", " "),
                        str(ev.llm_cost_usd),
                    ]
                )
        return buf.getvalue().encode("utf-8")

    async def export_pdf(self, run_id: UUID) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        run, tc = await self._load_run(run_id)
        criteria_by_id = {c.id: c for c in tc.criteria}

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=LETTER,
            leftMargin=0.6 * inch,
            rightMargin=0.6 * inch,
            topMargin=0.6 * inch,
            bottomMargin=0.6 * inch,
            title=f"Test Run {run_id}",
        )
        styles = getSampleStyleSheet()
        h1 = styles["Heading1"]
        h2 = styles["Heading2"]
        body = styles["BodyText"]
        small = ParagraphStyle(
            "small", parent=body, fontSize=8, textColor=colors.grey
        )

        story = []
        story.append(Paragraph(f"Test Run — {tc.name}", h1))
        story.append(
            Paragraph(
                f"Run ID: {run.id}<br/>"
                f"Status: {run.status.value}<br/>"
                f"Started: {run.started_at or '—'}<br/>"
                f"Completed: {run.completed_at or '—'}<br/>"
                f"Aggregate score: {run.aggregate_score or '—'}<br/>"
                f"Pass: {run.pass_}<br/>"
                f"Calls: {run.completed_calls}/{run.requested_calls} "
                f"(failed: {run.failed_calls})<br/>"
                f"Total cost: ${run.total_cost_usd}",
                body,
            )
        )
        story.append(Spacer(1, 12))

        if run.insights:
            story.append(Paragraph("Insights", h2))
            suggestions = run.insights.get("suggestions", [])
            if suggestions:
                for s in suggestions:
                    story.append(Paragraph(f"• {s}", body))
            top_issues = run.insights.get("top_issues", [])
            if top_issues:
                story.append(Spacer(1, 6))
                story.append(Paragraph("Top issues", body))
                for issue in top_issues:
                    story.append(
                        Paragraph(
                            f"<b>{issue.get('criterion', '')}</b> — "
                            f"{int(issue.get('fail_rate', 0) * 100)}% fail — "
                            f"{issue.get('summary', '')}",
                            body,
                        )
                    )
            story.append(Spacer(1, 12))

        story.append(Paragraph("Criteria", h2))
        crit_rows = [["Criterion", "Type", "Weight", "Max"]]
        for c in tc.criteria:
            crit_rows.append(
                [
                    c.name,
                    c.type.value,
                    str(c.weight),
                    str(c.max_score) if c.max_score is not None else "—",
                ]
            )
        t = Table(crit_rows, hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 12))

        for idx, call in enumerate(run.calls, start=1):
            story.append(
                Paragraph(
                    f"Call {idx} — {call.status.value}",
                    h2,
                )
            )
            story.append(
                Paragraph(
                    f"Duration: {call.duration_sec or '—'}s · "
                    f"Cost: ${call.cost_usd} · "
                    f"Retell: {call.retell_call_id or '—'}",
                    small,
                )
            )
            if call.transcript:
                # Truncate very long transcripts for size
                snippet = call.transcript[:3000]
                story.append(
                    Paragraph(snippet.replace("\n", "<br/>"), body)
                )
            story.append(Spacer(1, 6))
            if call.evaluations:
                ev_rows = [
                    ["Criterion", "Result", "Reasoning", "Confidence"]
                ]
                for ev in call.evaluations:
                    c = criteria_by_id.get(ev.criterion_id)
                    if c is None:
                        continue
                    if c.type.value == "boolean":
                        result = "Pass" if ev.passed else "Fail" if ev.passed is False else "—"
                    else:
                        result = (
                            f"{ev.score}/{c.max_score}"
                            if ev.score is not None
                            else "—"
                        )
                    ev_rows.append(
                        [
                            c.name,
                            result,
                            (ev.reasoning or "")[:240],
                            f"{float(ev.confidence):.2f}"
                            if ev.confidence is not None
                            else "—",
                        ]
                    )
                et = Table(
                    ev_rows,
                    colWidths=[1.4 * inch, 0.9 * inch, 3.8 * inch, 0.8 * inch],
                    hAlign="LEFT",
                )
                et.setStyle(
                    TableStyle(
                        [
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                        ]
                    )
                )
                story.append(et)
            story.append(Spacer(1, 12))

        doc.build(story)
        return buf.getvalue()
