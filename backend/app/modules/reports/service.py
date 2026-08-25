import csv
import io
from html import escape

from app.core.enums import Classification
from app.db.models.core import Report

CLASSIFICATION_RANK = {
    Classification.PUBLIC: 0,
    Classification.PARTNER: 1,
    Classification.INTERNAL: 2,
}


def safe_csv_cell(value: str) -> str:
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{value}"
    return value


def preserves_classification(source: Classification, output: Classification) -> bool:
    return CLASSIFICATION_RANK[output] >= CLASSIFICATION_RANK[source]


def report_csv(report: Report) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "report_id",
            "title",
            "classification",
            "reporting_period",
            "admin_unit_id",
            "boundary_version",
            "published_at",
        ]
    )
    writer.writerow(
        [
            report.id,
            safe_csv_cell(report.title),
            report.classification.value,
            report.reporting_period,
            report.admin_unit_id,
            report.boundary_version,
            report.published_at.isoformat() if report.published_at else "",
        ]
    )
    return output.getvalue()


def report_html(report: Report) -> str:
    """Render an inert, print-ready document from the authorized report projection."""
    sections = "".join(
        f"<section><h2>{escape(str(item['heading']))}</h2>"
        f"<p>{escape(str(item['body']))}</p></section>"
        for item in report.sections
    )
    findings = "".join(f"<li>{escape(str(item))}</li>" for item in report.findings)
    recommendations = "".join(
        f"<li>{escape(str(item))}</li>" for item in report.recommendations
    )
    published = report.published_at.isoformat() if report.published_at else "Not published"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{escape(report.title)}</title><style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:52rem;margin:3rem auto;padding:0 1.5rem;color:#17211b}}
header{{border-bottom:3px solid #18734f;margin-bottom:2rem}}dt{{font-weight:700}}dd{{margin:0 0 .75rem}}
@media print{{body{{margin:0;max-width:none}}}} </style></head><body>
<header><p>SOMALIA AI · GOVERNED SITUATION REPORT</p><h1>{escape(report.title)}</h1></header>
<dl><dt>Classification</dt><dd>{escape(report.classification.value.upper())}</dd>
<dt>Reporting period</dt><dd>{escape(report.reporting_period)}</dd>
<dt>Administrative unit ID</dt><dd>{report.admin_unit_id}</dd>
<dt>Boundary version</dt><dd>{escape(report.boundary_version)}</dd>
<dt>Published</dt><dd>{escape(published)}</dd></dl>{sections}
<section><h2>Findings</h2><ul>{findings or '<li>None recorded</li>'}</ul></section>
<section><h2>Recommendations</h2><ul>{recommendations or '<li>None recorded</li>'}</ul></section>
<footer><p>Decision-support report. Warning publication remains a separate human-governed process.</p>
<p>Report ID: {report.id}</p></footer></body></html>"""
