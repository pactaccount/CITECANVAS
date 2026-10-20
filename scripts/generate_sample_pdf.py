"""
Generate reproducible sample multi-page PDF fixture with tables, charts, and footnotes.
Matches test cases defined in fixtures/evaluation/ground_truth.json.
"""

from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.shapes import Drawing, Rect, String, Line


def build_sample_pdf(output_path: str):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1A365D"),
        spaceAfter=12,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#2D3748"),
    )
    footnote_style = ParagraphStyle(
        "ReportFootnote",
        parent=styles["Normal"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#718096"),
    )

    story = []

    # ==================== PAGE 1: Financial Table ====================
    story.append(Paragraph("Global Manufacturing Corp — Form 10-Q Segment Revenue Disclosure", title_style))
    story.append(Paragraph("For the Three Months Ended September 30, 2023 (Unaudited)", body_style))
    story.append(Spacer(1, 14))

    fin_data = [
        ["Revenue Stream / Financial Metric", "Three Months Ended\nSep 30, 2022", "Three Months Ended\nSep 30, 2023"],
        ["Automotive regulatory credits", "$286", "$554"],
        ["Total automotive revenues", "$17,785", "$19,625"],
        ["Energy generation and storage", "$1,117", "$1,559"],
        ["Services and other", "$1,645", "$2,166"],
        ["Total consolidated revenues", "$20,547", "$23,350"],
        ["GAAP Gross Margin (%)", "25.1%", "17.9%"],
    ]
    fin_table = Table(fin_data, colWidths=[240, 150, 150])
    fin_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F7FAFC"), colors.white]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(fin_table)
    story.append(Spacer(1, 16))
    story.append(Paragraph("Note 1: All dollar amounts are presented in USD Millions unless otherwise noted.", footnote_style))
    story.append(Paragraph("Note 2: Gross margin calculation excludes depreciation of production machinery.", footnote_style))

    from reportlab.platypus import PageBreak
    story.append(PageBreak())

    # ==================== PAGE 2: Engineering Specs ====================
    story.append(Paragraph("Industrial Hydraulics Division — Technical Data Sheet Model HP-400", title_style))
    story.append(Paragraph("Subsystem: Primary Actuation Unit & Pressure Specifications", body_style))
    story.append(Spacer(1, 14))

    eng_data = [
        ["Parameter / Specification Item", "Design Value", "Standard Unit / Tolerance"],
        ["Hydraulic Pump Model", "HP-400", "Heavy Duty Series"],
        ["Maximum Operating Pressure", "350", "bar"],
        ["Displacement per revolution", "45.0", "cc/rev (+/- 1.5%)"],
        ["Recommended Bolt Torque (M12 Flange)", "85", "Nm (+/- 3 Nm)"],
        ["Operating Temperature Range", "-20 to +85", "deg C"],
        ["Maximum Shaft Speed", "3600", "RPM"],
    ]
    eng_table = Table(eng_data, colWidths=[240, 150, 150])
    eng_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2D3748")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#EDF2F7"), colors.white]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(eng_table)
    story.append(Spacer(1, 16))
    story.append(Paragraph("Note 4: Approved hydraulic fluid specification is MIL-PRF-83282 synthetic hydrocarbon base.", footnote_style))
    story.append(Paragraph("Note 5: Torque values apply to lubricated threads with phosphate-treated fasteners.", footnote_style))

    story.append(PageBreak())

    # ==================== PAGE 3: Performance Benchmark ====================
    story.append(Paragraph("Edge Computing Benchmark Report — Gateway Performance", title_style))
    story.append(Paragraph("Measured Throughput and Latency Profiles across Connection Pools", body_style))
    story.append(Spacer(1, 14))

    # Add a mock chart drawing
    chart_drawing = Drawing(540, 160)
    chart_drawing.add(Rect(0, 0, 540, 160, fillColor=colors.HexColor("#F7FAFC"), strokeColor=colors.HexColor("#CBD5E0")))
    chart_drawing.add(String(20, 140, "Figure 2: Throughput (req/sec) vs Concurrent Connections", fontSize=11, fontName="Helvetica-Bold", fillColor=colors.HexColor("#2B6CB0")))
    # Bars
    conns = ["10 Conns", "25 Conns", "50 Conns", "100 Conns"]
    values = [4200, 9100, 14200, 13800]
    for idx, (conn, val) in enumerate(zip(conns, values)):
        bar_h = (val / 16000.0) * 80
        x = 50 + idx * 110
        y = 35
        chart_drawing.add(Rect(x, y, 60, bar_h, fillColor=colors.HexColor("#3182CE"), strokeColor=None))
        chart_drawing.add(String(x + 5, y + bar_h + 4, f"{val}", fontSize=9, fontName="Helvetica-Bold", fillColor=colors.HexColor("#2D3748")))
        chart_drawing.add(String(x + 5, y - 14, conn, fontSize=9, fontName="Helvetica", fillColor=colors.HexColor("#4A5568")))
    
    story.append(chart_drawing)
    story.append(Spacer(1, 16))

    perf_data = [
        ["Connection Pool", "Throughput (req/sec)", "p50 Latency (ms)", "p99 Latency (ms)"],
        ["10 Connections", "4200", "1.1", "2.4"],
        ["25 Connections", "9100", "1.4", "3.1"],
        ["50 Connections", "14200", "1.8", "4.5"],
        ["100 Connections", "13800", "2.9", "7.8"],
    ]
    perf_table = Table(perf_data, colWidths=[135, 135, 135, 135])
    perf_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#319795")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#E6FFFA"), colors.white]),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(perf_table)
    story.append(Spacer(1, 14))
    story.append(Paragraph("Conclusion: Peak throughput recorded at 50 concurrent connections in Figure 2 is 14200 req/sec. The p99 latency threshold under nominal load is 4.5 ms.", body_style))

    doc.build(story)
    print(f"Sample PDF successfully generated at: {output_path}")


if __name__ == "__main__":
    out_file = Path(__file__).resolve().parent.parent / "fixtures" / "evaluation" / "sample_tech_report.pdf"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    build_sample_pdf(str(out_file))
