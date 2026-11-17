"""Report generation: PDF, HTML and JSON.

Reports never contain passwords, PSKs or any other secret.  The renderer
receives only the sanitised audit payload produced by
:class:`~wififortress.services.audit_service.SecurityAuditService`, and a
final guard re-checks the text for secret patterns before writing.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from wififortress import APP_NAME, APP_VERSION, APP_LICENSE
from wififortress.core.database import Database
from wififortress.core.logging import get_logger
from wififortress.core.paths import reports_dir
from wififortress.core.redaction import redact_text

log = get_logger(__name__)

_SECRET_PATTERN = re.compile(
    r"(?i)(psk|passphrase|password|passwd)\s*[:=]\s*\S+"
)

SEVERITY_COLORS = {
    "Critical": "#EF5350",
    "High": "#F5B942",
    "Medium": "#00A8E8",
    "Low": "#00D4C7",
    "Informational": "#94AAB3",
    "Unknown": "#7A8C94",
}


@dataclass
class ReportPaths:
    pdf: Path | None = None
    html: Path | None = None
    json: Path | None = None


class ReportService:
    def __init__(self, db: Database | None = None, output_dir: Path | None = None) -> None:
        self.db = db or Database()
        self.output_dir = output_dir or reports_dir()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # -- public API ----------------------------------------------------
    def generate(
        self,
        audit: dict[str, Any],
        formats: tuple[str, ...] = ("pdf", "html", "json"),
        title: str | None = None,
    ) -> ReportPaths:
        safe = self._sanitise(audit)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        ssid_slug = re.sub(r"[^A-Za-z0-9_-]+", "_", (safe.get("ssid") or "network"))[:40]
        base = f"wifi-fortress-audit-{ssid_slug}-{stamp}"
        paths = ReportPaths()

        if "json" in formats:
            paths.json = self.output_dir / f"{base}.json"
            paths.json.write_text(
                json.dumps(safe, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self._register(paths.json, "audit", title or self._default_title(safe), safe, "json")

        if "html" in formats:
            paths.html = self.output_dir / f"{base}.html"
            paths.html.write_text(self.render_html(safe), encoding="utf-8")
            self._register(paths.html, "audit", title or self._default_title(safe), safe, "html")

        if "pdf" in formats:
            paths.pdf = self.output_dir / f"{base}.pdf"
            try:
                self.render_pdf(safe, paths.pdf)
                self._register(paths.pdf, "audit", title or self._default_title(safe), safe, "pdf")
            except Exception as exc:  # pragma: no cover - reportlab dependent
                log.error("PDF generation failed: %s", exc)
                paths.pdf = None
        return paths

    def generate_environment_report(
        self, payload: dict[str, Any], formats: tuple[str, ...] = ("pdf", "html", "json")
    ) -> ReportPaths:
        safe = self._sanitise(payload)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = f"wifi-fortress-environment-{stamp}"
        paths = ReportPaths()
        if "json" in formats:
            paths.json = self.output_dir / f"{base}.json"
            paths.json.write_text(json.dumps(safe, indent=2, ensure_ascii=False), encoding="utf-8")
            self._register(paths.json, "environment", "Wireless environment report", safe, "json")
        if "html" in formats:
            paths.html = self.output_dir / f"{base}.html"
            paths.html.write_text(self.render_environment_html(safe), encoding="utf-8")
            self._register(paths.html, "environment", "Wireless environment report", safe, "html")
        if "pdf" in formats:
            paths.pdf = self.output_dir / f"{base}.pdf"
            try:
                self.render_environment_pdf(safe, paths.pdf)
                self._register(paths.pdf, "environment", "Wireless environment report", safe, "pdf")
            except Exception as exc:  # pragma: no cover
                log.error("PDF generation failed: %s", exc)
                paths.pdf = None
        return paths

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.reports(limit)]

    def delete(self, report_id: int) -> bool:
        for row in self.db.reports(1000):
            if row["id"] != report_id:
                continue
            path = Path(row["path"])
            try:
                if path.exists():
                    path.unlink()
            except OSError as exc:
                log.warning("Could not delete report file %s: %s", path, exc)
            self.db.delete_report(report_id)
            return True
        return False

    def compare(self, audit_a: dict[str, Any], audit_b: dict[str, Any]) -> dict[str, Any]:
        from wififortress.services.audit_service import compare_audits

        return compare_audits(audit_a, audit_b)

    # -- sanitising ----------------------------------------------------
    @staticmethod
    def _sanitise(payload: dict[str, Any]) -> dict[str, Any]:
        text = json.dumps(payload, ensure_ascii=False, default=str)
        if _SECRET_PATTERN.search(text):
            text = redact_text(text)
            payload = json.loads(text)
        # Never carry these keys into a report.
        for key in ("password", "psk", "secret", "credential"):
            payload.pop(key, None)
        return payload

    @staticmethod
    def _default_title(audit: dict[str, Any]) -> str:
        return f"WiFi Fortress audit - {audit.get('ssid', 'network')}"

    def _register(
        self,
        path: Path,
        kind: str,
        title: str,
        payload: dict[str, Any],
        fmt: str,
    ) -> None:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            size = path.stat().st_size
        except OSError:
            digest, size = "", 0
        self.db.add_report(
            {
                "kind": kind,
                "title": title,
                "ssid": payload.get("ssid", ""),
                "score": payload.get("score"),
                "path": str(path),
                "format": fmt,
                "size_bytes": size,
                "sha256": digest,
            }
        )

    # -- HTML ----------------------------------------------------------
    def render_html(self, audit: dict[str, Any]) -> str:
        esc = html.escape
        findings = audit.get("findings", [])
        counts = audit.get("severity_counts", {})
        score = audit.get("score", 0)
        grade = audit.get("grade", "")
        created = audit.get("created_at", "")
        network = audit.get("network", {})
        adapter = audit.get("adapter", {})
        breakdown = audit.get("score_breakdown", [])
        checklist = audit.get("checklist", [])
        app_version = audit.get("app_version", APP_VERSION)

        rows = []
        for f in findings:
            color = SEVERITY_COLORS.get(f.get("severity", ""), "#94AAB3")
            rows.append(
                f"""
      <section class="finding">
        <header>
          <span class="sev" style="background:{color}">{esc(f.get('severity', ''))}</span>
          <h3>{esc(f.get('title', ''))}</h3>
          <span class="verify">{esc(f.get('verification', ''))}</span>
        </header>
        <dl>
          <dt>Evidence</dt><dd>{esc(f.get('evidence', ''))}</dd>
          <dt>Explanation</dt><dd>{esc(f.get('explanation', ''))}</dd>
          <dt>Potential impact</dt><dd>{esc(f.get('impact', ''))}</dd>
          <dt>Recommended correction</dt><dd>{esc(f.get('recommendation', ''))}</dd>
        </dl>
      </section>"""
            )

        breakdown_rows = "".join(
            f"<tr><td>{esc(item.get('title', ''))}</td><td>{esc(item.get('severity', ''))}</td>"
            f"<td class='num'>{item.get('points', 0)}</td></tr>"
            for item in breakdown
        )
        checklist_rows = "".join(f"<li>{esc(item)}</li>" for item in checklist)
        network_rows = "".join(
            f"<tr><th>{esc(str(k))}</th><td>{esc(str(v))}</td></tr>"
            for k, v in network.items()
        )
        adapter_rows = "".join(
            f"<tr><th>{esc(str(k))}</th><td>{esc(str(v))}</td></tr>"
            for k, v in adapter.items()
            if not isinstance(v, (dict, list))
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{esc(APP_NAME)} audit - {esc(str(audit.get('ssid', '')))}</title>
<style>
  :root {{
    --bg:#101820; --panel:#172630; --card:#1D303B; --accent:#00D4C7;
    --accent2:#00A8E8; --text:#EDF6F7; --muted:#94AAB3; --ok:#31C48D;
    --warn:#F5B942; --crit:#EF5350;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text);
    font-family: "DejaVu Sans", "Segoe UI", system-ui, sans-serif; line-height:1.5; }}
  .wrap {{ max-width: 1000px; margin: 0 auto; padding: 32px 28px 64px; }}
  header.masthead {{ display:flex; justify-content:space-between; align-items:flex-end;
    border-bottom: 2px solid var(--accent); padding-bottom: 16px; margin-bottom: 28px; }}
  h1 {{ margin:0; font-size: 26px; letter-spacing: .5px; }}
  h1 span {{ color: var(--accent); }}
  .meta {{ color: var(--muted); font-size: 13px; text-align:right; }}
  .scorecard {{ display:flex; gap:24px; align-items:center; background:var(--panel);
    border-radius:16px; padding:24px; margin-bottom:28px; }}
  .score {{ font-size:52px; font-weight:700; color:var(--accent); line-height:1; }}
  .grade {{ font-size:22px; color:var(--muted); }}
  .counts {{ display:flex; gap:10px; flex-wrap:wrap; }}
  .count {{ background:var(--card); border-radius:10px; padding:8px 14px; font-size:13px; }}
  .count b {{ display:block; font-size:19px; }}
  h2 {{ font-size:17px; text-transform:uppercase; letter-spacing:1.2px;
    color:var(--accent2); margin:34px 0 12px; }}
  table {{ width:100%; border-collapse:collapse; background:var(--panel);
    border-radius:12px; overflow:hidden; font-size:13.5px; }}
  th, td {{ text-align:left; padding:9px 12px; border-bottom:1px solid #223642;
    vertical-align:top; }}
  th {{ color:var(--muted); font-weight:500; width:38%; }}
  td.num {{ text-align:right; color:var(--crit); }}
  .finding {{ background:var(--panel); border-radius:12px; padding:16px 18px; margin-bottom:14px; }}
  .finding header {{ display:flex; gap:12px; align-items:center; margin-bottom:8px; }}
  .finding h3 {{ margin:0; font-size:15.5px; flex:1; }}
  .sev {{ color:#101820; font-weight:700; font-size:11.5px; padding:3px 9px;
    border-radius:999px; text-transform:uppercase; letter-spacing:.6px; }}
  .verify {{ color:var(--muted); font-size:11.5px; }}
  dl {{ margin:0; display:grid; grid-template-columns: 180px 1fr; gap:6px 14px; font-size:13.5px; }}
  dt {{ color:var(--muted); }}
  dd {{ margin:0; }}
  ul.checklist {{ background:var(--panel); border-radius:12px; padding:16px 16px 16px 34px; }}
  ul.checklist li {{ margin-bottom:7px; font-size:13.5px; }}
  footer {{ margin-top:40px; color:var(--muted); font-size:12px;
    border-top:1px solid #223642; padding-top:14px; }}
</style>
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <div>
      <h1>{esc(APP_NAME)} <span>Security Audit</span></h1>
      <div class="meta">{esc(str(audit.get('ssid', '')))} &middot; {esc(str(audit.get('bssid', '')))}</div>
    </div>
    <div class="meta">
      Generated {esc(str(created))}<br>
      Application version {esc(str(app_version))}<br>
      License {esc(APP_LICENSE)}
    </div>
  </header>

  <div class="scorecard">
    <div>
      <div class="score">{esc(str(score))}<span style="font-size:20px;color:#94AAB3">/100</span></div>
      <div class="grade">Grade {esc(str(grade))}</div>
    </div>
    <div class="counts">
      <div class="count">Critical<b>{counts.get('critical', 0)}</b></div>
      <div class="count">High<b>{counts.get('high', 0)}</b></div>
      <div class="count">Medium<b>{counts.get('medium', 0)}</b></div>
      <div class="count">Low<b>{counts.get('low', 0)}</b></div>
      <div class="count">Info<b>{counts.get('informational', 0)}</b></div>
      <div class="count">Unknown<b>{counts.get('unknown', 0)}</b></div>
    </div>
  </div>

  <h2>Network</h2>
  <table>{network_rows}</table>

  <h2>Adapter</h2>
  <table>{adapter_rows or '<tr><td>No adapter information was recorded.</td></tr>'}</table>

  <h2>Score breakdown</h2>
  <table>
    <tr><th>Finding</th><th>Severity</th><th style="text-align:right">Points</th></tr>
    {breakdown_rows or '<tr><td colspan="3">No deductions.</td></tr>'}
  </table>

  <h2>Findings</h2>
  {''.join(rows) or '<p>No findings were produced.</p>'}

  <h2>Improvement checklist</h2>
  <ul class="checklist">{checklist_rows}</ul>

  <footer>
    {esc(APP_NAME)} {esc(str(app_version))} &middot; Defensive audit only. This report contains no
    passwords or other credentials. Findings marked "Unknown - not determinable" were not
    scored, because missing information is neither proof of security nor of vulnerability.
  </footer>
</div>
</body>
</html>
"""

    def render_environment_html(self, payload: dict[str, Any]) -> str:
        esc = html.escape
        networks = payload.get("networks", [])
        rows = "".join(
            "<tr>"
            f"<td>{esc(str(n.get('ssid', '')))}</td>"
            f"<td>{esc(str(n.get('bssid', '')))}</td>"
            f"<td>{esc(str(n.get('band', '')))}</td>"
            f"<td class='num'>{esc(str(n.get('channel', '')))}</td>"
            f"<td class='num'>{esc(str(n.get('signal', '')))}</td>"
            f"<td>{esc(str(n.get('security', '')))}</td>"
            "</tr>"
            for n in networks
        )
        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{esc(APP_NAME)} wireless environment</title>
<style>
 body {{ background:#101820; color:#EDF6F7; font-family:"DejaVu Sans",sans-serif;
   margin:0; padding:32px; }}
 h1 {{ color:#00D4C7; font-size:24px; }}
 table {{ width:100%; border-collapse:collapse; font-size:13.5px; background:#172630;
   border-radius:12px; overflow:hidden; }}
 th, td {{ padding:8px 11px; border-bottom:1px solid #223642; text-align:left; }}
 th {{ color:#94AAB3; font-weight:500; }}
 td.num {{ text-align:right; }}
</style></head><body>
<h1>{esc(APP_NAME)} - Wireless environment</h1>
<p style="color:#94AAB3">Generated {esc(str(payload.get('created_at', '')))} &middot;
{len(networks)} networks observed</p>
<table>
<tr><th>SSID</th><th>BSSID</th><th>Band</th><th style="text-align:right">Channel</th>
<th style="text-align:right">Signal (dBm)</th><th>Security</th></tr>
{rows}
</table>
<p style="color:#94AAB3;font-size:12px;margin-top:22px">
Channel observations come from beacon information elements. This is not RF spectrum analysis.
</p>
</body></html>
"""

    # -- PDF -----------------------------------------------------------
    def render_pdf(self, audit: dict[str, Any], path: Path) -> Path:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            KeepTogether,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        styles = getSampleStyleSheet()
        body = ParagraphStyle(
            "Body", parent=styles["BodyText"], fontSize=9.2, leading=12.6,
            textColor=colors.HexColor("#1D303B"),
        )
        small = ParagraphStyle("Small", parent=body, fontSize=8, leading=10.5,
                               textColor=colors.HexColor("#5A6B73"))
        h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=20,
                            textColor=colors.HexColor("#0E7C74"), spaceAfter=4)
        h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12.5,
                            textColor=colors.HexColor("#0E7C74"), spaceBefore=14, spaceAfter=6)
        label = ParagraphStyle("Label", parent=body, fontSize=8.4,
                               textColor=colors.HexColor("#5A6B73"))

        doc = SimpleDocTemplate(
            str(path), pagesize=A4,
            leftMargin=18 * mm, rightMargin=18 * mm,
            topMargin=16 * mm, bottomMargin=16 * mm,
            title=f"{APP_NAME} audit - {audit.get('ssid', '')}",
            author=APP_NAME, subject="Wireless security audit",
        )
        story: list = []
        story.append(Paragraph(f"{APP_NAME} - Wireless Security Audit", h1))
        story.append(Paragraph(
            f"Network: <b>{html.escape(str(audit.get('ssid', '')))}</b> "
            f"({html.escape(str(audit.get('bssid', '')))}) &nbsp;|&nbsp; "
            f"Interface: {html.escape(str(audit.get('interface', '')))}", body))
        story.append(Paragraph(
            f"Generated {html.escape(str(audit.get('created_at', '')))} &middot; "
            f"version {html.escape(str(audit.get('app_version', APP_VERSION)))}", small))
        story.append(Spacer(1, 8))

        counts = audit.get("severity_counts", {})
        score_table = Table(
            [
                ["Score", "Grade", "Critical", "High", "Medium", "Low", "Info", "Unknown"],
                [
                    f"{audit.get('score', 0)}/100",
                    str(audit.get("grade", "")),
                    str(counts.get("critical", 0)),
                    str(counts.get("high", 0)),
                    str(counts.get("medium", 0)),
                    str(counts.get("low", 0)),
                    str(counts.get("informational", 0)),
                    str(counts.get("unknown", 0)),
                ],
            ],
            colWidths=[26 * mm, 18 * mm, 22 * mm, 16 * mm, 20 * mm, 16 * mm, 16 * mm, 22 * mm],
        )
        score_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D303B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#EDF6F7")),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#EAF6F5")),
            ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#101820")),
            ("FONTSIZE", (0, 0), (-1, -1), 8.4),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B7C9CF")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(score_table)

        story.append(Paragraph("Network details", h2))
        net_rows = [[Paragraph("Field", label), Paragraph("Value", label)]]
        for key, value in (audit.get("network") or {}).items():
            net_rows.append([Paragraph(html.escape(str(key)), body),
                             Paragraph(html.escape(str(value)), body)])
        story.append(self._styled_table(net_rows, [45 * mm, 125 * mm]))

        adapter = audit.get("adapter") or {}
        if adapter:
            story.append(Paragraph("Adapter", h2))
            rows = [[Paragraph("Field", label), Paragraph("Value", label)]]
            for key, value in adapter.items():
                if isinstance(value, (dict, list)):
                    continue
                rows.append([Paragraph(html.escape(str(key)), body),
                             Paragraph(html.escape(str(value)), body)])
            story.append(self._styled_table(rows, [45 * mm, 125 * mm]))

        story.append(PageBreak())
        story.append(Paragraph("Findings", h2))
        for finding in audit.get("findings", []):
            block = [
                Paragraph(
                    f"<b>{html.escape(finding.get('title', ''))}</b> &nbsp; "
                    f"<font color='#0E7C74'>[{html.escape(finding.get('severity', ''))}]</font> "
                    f"<font size=7.5 color='#5A6B73'>{html.escape(finding.get('verification', ''))}</font>",
                    body,
                ),
                Paragraph(f"<b>Evidence:</b> {html.escape(finding.get('evidence', ''))}", body),
                Paragraph(f"<b>Explanation:</b> {html.escape(finding.get('explanation', ''))}", body),
                Paragraph(f"<b>Impact:</b> {html.escape(finding.get('impact', ''))}", body),
                Paragraph(f"<b>Correction:</b> {html.escape(finding.get('recommendation', ''))}", body),
                Spacer(1, 6),
            ]
            story.append(KeepTogether(block))
        if not audit.get("findings"):
            story.append(Paragraph("No findings were produced.", body))

        breakdown = audit.get("score_breakdown", [])
        if breakdown:
            story.append(Paragraph("Score breakdown", h2))
            rows = [[Paragraph("Finding", label), Paragraph("Severity", label),
                     Paragraph("Points", label)]]
            for item in breakdown:
                rows.append([
                    Paragraph(html.escape(item.get("title", "")), body),
                    Paragraph(html.escape(item.get("severity", "")), body),
                    Paragraph(str(item.get("points", 0)), body),
                ])
            story.append(self._styled_table(rows, [110 * mm, 35 * mm, 25 * mm]))

        checklist = audit.get("checklist", [])
        if checklist:
            story.append(Paragraph("Improvement checklist", h2))
            for item in checklist:
                story.append(Paragraph(f"&#9744;&nbsp; {html.escape(item)}", body))

        story.append(Spacer(1, 12))
        story.append(Paragraph(
            "This report contains no passwords or credentials. Findings marked "
            "&quot;Unknown - not determinable&quot; were not scored. Defensive audit only.",
            small,
        ))
        doc.build(story)
        return path

    def render_environment_pdf(self, payload: dict[str, Any], path: Path) -> Path:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        styles = getSampleStyleSheet()
        body = styles["BodyText"]
        body.fontSize = 8.5
        doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=16 * mm,
                                rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                                title=f"{APP_NAME} environment report")
        networks = payload.get("networks", [])
        data = [["SSID", "BSSID", "Band", "Ch", "Signal", "Security"]]
        for n in networks:
            data.append([
                Paragraph(html.escape(str(n.get("ssid", ""))), body),
                str(n.get("bssid", "")),
                str(n.get("band", "")),
                str(n.get("channel", "")),
                str(n.get("signal", "")),
                Paragraph(html.escape(str(n.get("security", ""))), body),
            ])
        table = Table(data, colWidths=[45 * mm, 33 * mm, 20 * mm, 12 * mm, 18 * mm, 40 * mm],
                      repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D303B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7.6),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B7C9CF")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story = [
            Paragraph(f"<b>{APP_NAME} - Wireless environment</b>", styles["Heading1"]),
            Paragraph(f"Generated {payload.get('created_at', '')} - {len(networks)} networks", body),
            Spacer(1, 8),
            table,
            Spacer(1, 10),
            Paragraph("Channel observations are derived from beacon information elements; "
                      "this is not RF spectrum analysis.", body),
        ]
        doc.build(story)
        return path

    @staticmethod
    def _styled_table(rows, widths):
        from reportlab.lib import colors
        from reportlab.platypus import Table, TableStyle

        table = Table(rows, colWidths=widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D303B")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B7C9CF")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        return table
