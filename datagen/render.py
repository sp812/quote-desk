"""Render the full fabricated dataset to ../data. Run: python3 render.py"""
import csv, json, os, shutil
from pathlib import Path
from spec import BUYER, RFX, LINES, QUESTIONNAIRE, FREIGHT_BENCHMARK_INR_PER_KG, USD_INR
from vendors import (VENDORS, ALL, QA, delivered, LINE_BY_ID, B_DISCOUNT, B_DISCOUNT_THRESHOLD_INR,
                     C_MISSING, C_DOWNGRADE, C_PER_STRIP, D_RATE, D_BLUR, D_FOUR_COL, D_WR_COAT, D_NOT_SUPPLIED,
                     E_EXPLICIT, E_LASTYEAR_LINES, e_usd, FY26_USD_INR)

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent / "data"
if ROOT.exists():
    shutil.rmtree(ROOT)
for d in ["rfx", "buyer_records", "inbox", "answer_key"]:
    (ROOT / d).mkdir(parents=True)

SS = getSampleStyleSheet()
small = ParagraphStyle("small", parent=SS["Normal"], fontSize=8, leading=10)
tiny = ParagraphStyle("tiny", parent=SS["Normal"], fontSize=6, leading=7.5, textColor=colors.HexColor("#555555"))
cell = ParagraphStyle("cell", parent=SS["Normal"], fontSize=7.5, leading=9)

Q = {v: f() for v, f in ALL.items()}

# =============================== RFx =========================================
def render_rfx():
    with open(ROOT / "rfx/line_items.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["line_id", "description", "style", "ply", "dimensions_mm", "flute", "board_spec", "print",
                    "target_weight_kg", "annual_qty", "uom"])
        for l in LINES:
            w.writerow([l[0], l[1], l[2], l[3], l[4], l[5], l[6], l[7], l[8], l[9], l[11]])
    with open(ROOT / "rfx/questionnaire.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["q_id", "question", "type", "pass_criterion"])
        w.writerows(QUESTIONNAIRE)

    # Quote template the vendors were asked to use (and mostly ignore)
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook(); ws = wb.active; ws.title = "Price Bid"
    ws.append([f"{RFX['id']} - {RFX['title']}"]); ws["A1"].font = Font(bold=True, size=12)
    ws.append([f"Price basis: {RFX['price_basis']}. Do not change line IDs."]); ws.append([])
    hdr = ["Line ID", "Description", "Dimensions (mm)", "Ply", "Board spec", "Print", "UoM", "Annual Qty",
           "Unit Price (INR, ex-GST, FOR Waluj)", "Lead time (days)", "Remarks / deviations"]
    ws.append(hdr)
    for c in ws[4]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1F3A5F")
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for l in LINES:
        ws.append([l[0], l[1], l[4], l[3], l[6], l[7], l[11], l[9], None, None, None])
    for col, wd in zip("ABCDEFGHIJK", [8, 52, 16, 5, 30, 12, 6, 11, 20, 10, 30]):
        ws.column_dimensions[col].width = wd
    q = wb.create_sheet("Questionnaire")
    q.append(["Q ID", "Question", "Type", "Your answer"])
    for r in QUESTIONNAIRE:
        q.append([r[0], r[1], r[2], None])
    q.column_dimensions["B"].width = 80
    wb.save(ROOT / "rfx/RFQ_quote_template.xlsx")

    # RFx PDF
    doc = SimpleDocTemplate(str(ROOT / f"rfx/{RFX['id']}.pdf"), pagesize=A4, leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    el = [Paragraph(f"<b>{BUYER['name']}</b>", SS["Title"]),
          Paragraph(f"Request for Quotation <b>{RFX['id']}</b>", SS["Heading2"]),
          Paragraph(RFX["title"], SS["Normal"]), Spacer(1, 6)]
    meta = [["Issued", RFX["issued"], "Bids due", RFX["due"]],
            ["Contract period", RFX["contract_period"], "Currency", RFX["currency"]],
            ["Price basis", RFX["price_basis"], "", ""],
            ["Payment terms", RFX["payment_terms_requested"], "Freight", RFX["freight"]],
            ["Delivery", BUYER["plant"], "", ""],
            ["Buyer", BUYER["buyer"], "Email", BUYER["email"]]]
    t = Table([[Paragraph(str(c), small) for c in r] for r in meta], colWidths=[28*mm, 72*mm, 22*mm, 58*mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF2F7")),
                           ("SPAN", (1, 2), (3, 2)), ("SPAN", (1, 4), (3, 4))]))
    el += [t, Spacer(1, 8), Paragraph("<b>1. Scope</b>", SS["Heading4"]),
           Paragraph("Supply of corrugated shippers, trays, partitions and pads for the Waluj brewery under an annual rate "
                     "contract. Quantities are annual estimates; call-offs are weekly with peak demand March-May. Award may be "
                     "split by line. Boxes must meet the specified board grade and pass BCT testing per DPB packaging standard PS-04.",
                     small),
           Paragraph("<b>2. Line items</b>", SS["Heading4"])]
    rows = [["ID", "Description", "Dims (mm)", "Ply", "Board", "Print", "Wt kg", "Annual qty"]]
    for l in LINES:
        rows.append([l[0], Paragraph(l[1], cell), l[4], l[3] or "-", Paragraph(l[6], cell), l[7], f"{l[8]:.3f}", f"{l[9]:,} {l[11]}"])
    t = Table(rows, colWidths=[10*mm, 55*mm, 24*mm, 8*mm, 33*mm, 17*mm, 12*mm, 22*mm], repeatRows=1)
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    el += [t, Paragraph("<b>3. Supplier questionnaire</b> (mandatory items are pass/fail)", SS["Heading4"])]
    rows = [["Q", "Question", "Type", "Pass criterion"]] + [[a, Paragraph(b, cell), c, Paragraph(d, cell)] for a, b, c, d in QUESTIONNAIRE]
    t = Table(rows, colWidths=[9*mm, 105*mm, 20*mm, 46*mm])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2F7"))]))
    el += [t, Paragraph("<b>4. Evaluation</b>", SS["Heading4"]),
           Paragraph("Only suppliers passing all mandatory questionnaire items are eligible. Among eligible suppliers, award is "
                     "on lowest landed cost per line (price + freight to Waluj, net of discounts, ex-GST). Please quote in the "
                     "attached template. Quotes in other formats will be accepted but may take longer to evaluate.", small)]
    doc.build(el)

# ========================== Buyer records ====================================
def render_buyer_records():
    with open(ROOT / "buyer_records/freight_benchmarks.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["lane", "inr_per_kg", "basis"])
        for k, v in FREIGHT_BENCHMARK_INR_PER_KG.items():
            w.writerow([k, v, "FY26 logistics rate card, part-truck load"])
    # Last year's awarded contract prices (FY2025-26). Nordvik held 18 lines in USD.
    from spec import fair_price, noise
    with open(ROOT / "buyer_records/fy26_contract_prices.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["line_id", "fy26_description", "fy26_vendor", "currency", "fy26_unit_price", "uom", "fy26_fx_usd_inr", "notes"])
        for l in LINES:
            lid = l[0]
            if lid in E_LASTYEAR_LINES:
                w.writerow([lid, l[1], "Nordvik Packaging India Pvt. Ltd.", "USD", e_usd(lid), l[11], FY26_USD_INR, "FOR Bhiwandi; freight extra"])
            elif lid in E_EXPLICIT:
                w.writerow([lid, l[1], "Nordvik Packaging India Pvt. Ltd.", "USD", round(e_usd(lid) * 1.10, 3), l[11], FY26_USD_INR, "FOR Bhiwandi; freight extra"])
            elif lid in ("L28", "L29", "L30", "L25"):
                w.writerow([lid, l[1], "", "", "", l[11], "", "New line in FY27 - no history"])
            else:
                w.writerow([lid, l[1], "Indrayani Corrupack Pvt. Ltd.", "INR", round(fair_price(l) * 1.09 * noise("FY26", lid), 2), l[11], "", "FOR Waluj"])

# ============================ Vendor A: Excel ================================
def render_a():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    v = VENDORS["A"]; d = ROOT / "inbox/vendor_A_indrayani"; d.mkdir()
    wb = Workbook(); ws = wb.active; ws.title = "Quotation"
    ws.merge_cells("A1:H1"); ws["A1"] = "INDRAYANI CORRUPACK PVT. LTD."
    ws["A1"].font = Font(bold=True, size=16, color="8B1A1A"); ws["A1"].alignment = Alignment(horizontal="center")
    ws.merge_cells("A2:H2"); ws["A2"] = "Gat No. 312, Kharabwadi, Chakan, Pune 410501 | GSTIN 27AAFCI5521K1ZQ | Mfrs. of Corrugated Boxes since 1998"
    ws["A2"].alignment = Alignment(horizontal="center"); ws["A2"].font = Font(size=9, italic=True)
    ws.merge_cells("A4:H4"); ws["A4"] = f"Quotation No. ICP/Q/26-27/0418  dt. 06.10.2026   |   Kind Attn: Ms. Priya Kulkarni, Deccan Peak Breweries - Waluj"
    ws["A4"].font = Font(bold=True, size=10)
    hdr = ["Sr.", "Our Code", "Item", "Size L x W x H (mm)", "Ply / Grade", "Printing", "Rate / 100 Nos (Rs.)", "Remarks"]
    ws.append([]); ws.append(hdr)
    for c in ws[6]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="8B1A1A")
        c.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
    # Their own grouping and wording, not the RFx order
    order = sorted(LINES, key=lambda l: ({"5P_PRINT": 0, "5P_PLAIN": 1, "7P": 2, "3P_PRINT": 3, "3P_PLAIN": 4,
                                          "TRAY": 5, "PARTITION": 6, "PAD": 7}[l[10]], l[0]))
    names = {
        "L01": "Classic Lager 650x12 shipper", "L02": "Strong 650x12 shipper", "L03": "Wheat 650x12 (premium) shipper",
        "L04": "Classic 330 btl x24", "L05": "Classic CAN 330 x24", "L06": "Strong CAN 500 x24", "L07": "Wheat CAN 500 x24",
        "L08": "650x12 PLAIN (CB)", "L09": "330 CAN x24 PLAIN", "L10": "Master ctn 4x6 can 330", "L11": "Master ctn 4x6 can 500",
        "L12": "Gift pack outer 2x650", "L13": "GP spares ctn small", "L14": "GP spares ctn large", "L15": "Tray 24 can 330 (shrink)",
        "L16": "Tray 24 can 500 (shrink)", "L17": "Display tray 12x650 MT", "L18": "Partition 12 cell 650ml (set)",
        "L19": "Partition 24 cell 330ml (set)", "L20": "Layer pad 1000x1200", "L21": "Layer pad 1100x1100 export",
        "L22": "Top-bottom pad 650 shipper", "L23": "Edge board 50x50x5 1 mtr", "L24": "Keg collar 30L",
        "L25": "IPL promo 650x12 (4 col)", "L26": "QA sample ctn 6x650", "L27": "Crate liner", "L28": "EXPORT 650x12 7ply",
        "L29": "EXPORT can 330x24 7ply", "L30": "Cold chain 650x12 WR coated"}
    r = 7
    for i, l in enumerate(order, 1):
        lid = l[0]; q = Q["A"][lid]
        code = f"ICP-{['', '', '', 'C3', '', 'C5', '', 'C7'][l[3]] if l[3] in (3, 5, 7) else 'EB'}-{100 + int(lid[1:]) * 7}"
        grade = f"{l[3]} ply / {l[6].split(',')[0].replace(' top','')}" if l[3] else "Laminated"
        ws.append([i, code, names[lid], l[4].replace("x", " x "), grade, l[7].replace(" flexo", ""), int(q["raw_value"]),
                   "" if lid not in ("L30",) else "WR coating incl."])
        r += 1
    ws.append([])
    terms = ["TERMS & CONDITIONS:", "1. Rates are per 100 Nos. and F.O.R. your Waluj plant.", "2. GST @ 18% extra as applicable.",
             "3. Payment: 45 days from date of invoice.", "4. Delivery: 7 days from receipt of confirmed PO / artwork approval.",
             "5. Rates valid for 12 months subject to kraft paper price variation beyond +/- 5% (linked to IPPTA index).",
             "6. Tolerance on quantity +/- 5%.", "", "For INDRAYANI CORRUPACK PVT. LTD.", "Rahul Deshmukh - Sr. Manager, Sales | +91 98220 4XXXX"]
    for t in terms:
        ws.append([t]); ws.cell(row=ws.max_row, column=1).font = Font(bold=(t.startswith("TERMS") or t.startswith("For")), size=9)
    for col, wd in zip("ABCDEFGH", [5, 13, 30, 20, 22, 10, 14, 18]):
        ws.column_dimensions[col].width = wd
    s2 = wb.create_sheet("Compliance")
    s2.append(["Vendor compliance declaration - Indrayani Corrupack"]); s2["A1"].font = Font(bold=True)
    s2.append(["Point", "Our response"])
    qa = QA["A"]
    for qid, text, *_ in QUESTIONNAIRE:
        s2.append([text, qa[qid]])
    s2.column_dimensions["A"].width = 80; s2.column_dimensions["B"].width = 40
    wb.save(d / "Indrayani_Quotation_DeccanPeak_2026-27.xlsx")

    (d / "email.txt").write_text(
        f"From: {v['contact']} <{v['email']}>\nTo: {BUYER['email']}\nDate: Tue, 6 Oct 2026 18:42 +0530\n"
        f"Subject: RE: {RFX['id']} - Quotation for corrugated boxes FY 26-27\nAttachments: Indrayani_Quotation_DeccanPeak_2026-27.xlsx, ICP_BCT_Test_Report_Sep26.pdf, ICP_ISO9001_Certificate.pdf\n\n"
        "Dear Madam,\n\nGreetings from Indrayani Corrupack!\n\nPlease find attached our best quotation against your enquiry along with our "
        "compliance sheet (2nd tab), our ISO 9001 certificate and latest BCT test report for your Classic shipper.\n\nWe have quoted all 30 items. We have used our "
        "standard quotation format for internal reasons, kindly bear with us.\n\nWe value our long association with Deccan Peak and look forward "
        "to continuing as your partner.\n\nWarm regards,\nRahul Deshmukh\nSr. Manager - Sales\nIndrayani Corrupack Pvt. Ltd.\n")

    # Attachment: BCT test report
    render_a_iso(d)
    doc = SimpleDocTemplate(str(d / "ICP_BCT_Test_Report_Sep26.pdf"), pagesize=A4)
    rows = [["Parameter", "Specification", "Result", "Status"],
            ["Box Compression (BCT), kgf", ">= 450", "512", "PASS"], ["Bursting strength, kg/cm2", ">= 11.0", "12.4", "PASS"],
            ["Edge Crush (ECT), kN/m", ">= 6.5", "7.1", "PASS"], ["Moisture content, %", "7 - 9", "7.8", "PASS"],
            ["Board GSM (total)", ">= 690", "702", "PASS"]]
    t = Table(rows); t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE"))]))
    doc.build([Paragraph("Indrayani Corrupack Pvt. Ltd. - QC Laboratory", SS["Title"]),
               Paragraph("Test Report No. ICP/QC/2026/0917 | Date: 22-09-2026 | Sample: 5-ply RSC 375x285x300 (Classic Lager 650x12)", small),
               Spacer(1, 10), t, Spacer(1, 10),
               Paragraph("Tested in-house on Universal Box Compression Tester (Cap. 2000 kgf), calibrated 04-2026. Conditioning: 27 C / 65% RH for 24 h.", small),
               Spacer(1, 20), Paragraph("Checked by: QC Executive &nbsp;&nbsp;&nbsp; Approved by: QA Manager", small)])

def render_a_iso(d):
    doc = SimpleDocTemplate(str(d / "ICP_ISO9001_Certificate.pdf"), pagesize=A4, topMargin=40*mm)
    big = ParagraphStyle("big", parent=SS["Title"], fontSize=22, leading=28)
    cen = ParagraphStyle("cen", parent=SS["Normal"], alignment=1, fontSize=11, leading=16)
    doc.build([Paragraph("CERTIFICATE OF REGISTRATION", big), Spacer(1, 10),
               Paragraph("This is to certify that the Quality Management System of", cen), Spacer(1, 6),
               Paragraph("<b>INDRAYANI CORRUPACK PVT. LTD.</b><br/>Gat No. 312, Kharabwadi, Chakan, Pune 410501", cen),
               Spacer(1, 10), Paragraph("has been assessed and found to conform to the requirements of", cen),
               Paragraph("<b>ISO 9001:2015</b>", big),
               Paragraph("Scope: Design and manufacture of corrugated boxes, trays, partitions and pads", cen), Spacer(1, 24),
               Paragraph("Certificate No.: QMS/IN/25/51988 &nbsp;&nbsp; Original approval: 15-Mar-2019", cen),
               Paragraph("Date of issue: 15-Mar-2025 &nbsp;&nbsp; <b>Valid until: 14-Mar-2028</b>", cen),
               Paragraph("Validity subject to successful surveillance audits.", cen), Spacer(1, 30),
               Paragraph("Issued by: Meridian Assurance Services Pvt. Ltd. (fictional certification body)", cen)])


# ============================== Vendor B: PDF ================================
def render_b():
    v = VENDORS["B"]; d = ROOT / "inbox/vendor_B_seabreeze"; d.mkdir()
    def letterhead(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#0B5563")); canvas.rect(0, A4[1] - 30*mm, A4[0], 30*mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white); canvas.setFont("Helvetica-Bold", 18)
        canvas.drawString(15*mm, A4[1] - 15*mm, "SEABREEZE PACKAGING INDUSTRIES")
        canvas.setFont("Helvetica", 8)
        canvas.drawString(15*mm, A4[1] - 21*mm, "Survey No. 88/2, Kachigam Industrial Area, Nani Daman 396210 (U.T. of DNH & DD)  |  GSTIN 25ABMFS7712R1Z3")
        canvas.drawString(15*mm, A4[1] - 25*mm, "ISO 9001 Certified  |  FSC Mix  |  www.seabreezepack.example")
        canvas.setFillColor(colors.HexColor("#0B5563")); canvas.setFont("Helvetica", 7)
        canvas.drawString(15*mm, 8*mm, f"Page {doc.page}  -  Seabreeze Packaging Industries - Commercial offer SPI/2026/DPB/112")
        canvas.restoreState()
    doc = SimpleDocTemplate(str(d / "Seabreeze_Commercial_Offer_SPI-2026-DPB-112.pdf"), pagesize=A4,
                            topMargin=36*mm, leftMargin=15*mm, rightMargin=15*mm, bottomMargin=18*mm)
    el = [Paragraph("Ref: SPI/2026/DPB/112 &nbsp;&nbsp;&nbsp;&nbsp; Date: 07 October 2026", small), Spacer(1, 4),
          Paragraph("To,<br/>The Category Manager - Packaging<br/>Deccan Peak Breweries Ltd., Waluj", small), Spacer(1, 6),
          Paragraph(f"<b>Sub: Commercial offer against your RFQ {RFX['id']}</b>", small), Spacer(1, 4),
          Paragraph("Dear Madam, with reference to the above RFQ we are pleased to submit our most competitive rates for your "
                    "esteemed consideration. All items will be manufactured strictly as per your specification.", small), Spacer(1, 6)]
    rows = [["Sr", "Item description", "Size (mm)", "Ply", "Rate (Rs/pc)*"]]
    for i, l in enumerate(LINES, 1):
        q = Q["B"][l[0]]
        desc = l[1].replace("Shipper", "RSC Box").replace("Deccan ", "")
        rows.append([str(i), Paragraph(desc, cell), l[4], str(l[3]) if l[3] else "-", f"{q['raw_value']:.2f}"])
    t = Table(rows, colWidths=[9*mm, 95*mm, 32*mm, 10*mm, 26*mm], repeatRows=1)
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9DB4BA")),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B5563")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("ALIGN", (4, 1), (4, -1), "RIGHT")]))
    el += [t, Spacer(1, 8), Paragraph("<b>Commercial terms</b>", SS["Heading5"]),
           Paragraph("1. Prices are <b>Ex-works Daman</b>. Freight and transit insurance at actuals, to be borne by buyer.<br/>"
                     "2. GST @ 18% extra.<br/>3. Payment: 30 days from date of invoice.<br/>4. Delivery: 8-9 days from PO.<br/>"
                     "5. Validity: 90 days. Prices subject to revision in case of kraft paper increase above 5%.<br/>"
                     "6. Minimum order per call-off: one full truck (approx. 6 MT) or freight surcharge applies.", small),
           Spacer(1, 8), Paragraph("<b>Response to supplier questionnaire</b>", SS["Heading5"])]
    qa = QA["B"]
    el.append(Paragraph("<br/>".join(f"{qid}. {txt} &mdash; <i>{qa[qid]}</i>" for qid, txt, *_ in QUESTIONNAIRE), small))
    el += [Spacer(1, 14), Paragraph("Thanking you and assuring you of our best services,<br/><br/>For Seabreeze Packaging Industries<br/>"
                                   "<b>Mehul Shah</b>, Partner", small), Spacer(1, 30),
           Paragraph(f"* A trade discount of {int(B_DISCOUNT*100)}% shall be extended on the total invoice value if the cumulative annual order "
                     "value placed on us exceeds Rs. 50,00,000 (Rupees fifty lakh), settled quarterly by credit note. E.&amp;O.E.", tiny)]
    doc.build(el, onFirstPage=letterhead, onLaterPages=letterhead)

    (d / "email.txt").write_text(
        f"From: {v['contact']} <{v['email']}>\nTo: {BUYER['email']}\nDate: Wed, 7 Oct 2026 16:05 +0530\n"
        f"Subject: Offer - {RFX['id']}\nAttachments: Seabreeze_Commercial_Offer_SPI-2026-DPB-112.pdf, Seabreeze_ISO9001_Certificate.pdf\n\n"
        "Dear Priya ji,\n\nPlease find our offer attached. ISO certificate also attached for your records.\n\n"
        "Kindly note we are an approved supplier to two leading breweries in Gujarat and can support your peak season.\n\n"
        "Regards,\nMehul Shah\nSeabreeze Packaging Industries\n")

    # ISO certificate - EXPIRED before contract start
    doc = SimpleDocTemplate(str(d / "Seabreeze_ISO9001_Certificate.pdf"), pagesize=A4, topMargin=40*mm)
    big = ParagraphStyle("big", parent=SS["Title"], fontSize=22, leading=28)
    cen = ParagraphStyle("cen", parent=SS["Normal"], alignment=1, fontSize=11, leading=16)
    doc.build([Paragraph("CERTIFICATE OF REGISTRATION", big), Spacer(1, 10),
               Paragraph("This is to certify that the Quality Management System of", cen), Spacer(1, 6),
               Paragraph("<b>SEABREEZE PACKAGING INDUSTRIES</b><br/>Survey No. 88/2, Kachigam Industrial Area, Nani Daman 396210", cen),
               Spacer(1, 10), Paragraph("has been assessed and found to conform to the requirements of", cen),
               Paragraph("<b>ISO 9001:2015</b>", big),
               Paragraph("Scope: Manufacture and supply of corrugated boxes, sheets and allied packaging products", cen), Spacer(1, 24),
               Paragraph("Certificate No.: QMS/IN/23/40712 &nbsp;&nbsp; Original approval: 01-Sep-2023", cen),
               Paragraph("Date of issue: 01-Sep-2023 &nbsp;&nbsp; <b>Valid until: 31-Aug-2026</b>", cen),
               Paragraph("Validity subject to successful surveillance audits.", cen), Spacer(1, 30),
               Paragraph("Issued by: Meridian Assurance Services Pvt. Ltd. (fictional certification body)", cen)])

# ============================== Vendor C: Word ===============================
def render_c():
    from docx import Document
    from docx.shared import Pt
    v = VENDORS["C"]; d = ROOT / "inbox/vendor_C_kaveri"; d.mkdir()
    q = Q["C"]
    def r(lid): return f"Rs. {q[lid]['raw_value']:.2f}"
    doc = Document()
    st = doc.styles["Normal"]; st.font.name = "Calibri"; st.font.size = Pt(11)
    doc.add_heading("KAVERI KRAFTLINE PVT. LTD.", level=1)
    doc.add_paragraph("SIPCOT Phase II, Hosur 635109, Tamil Nadu  |  GSTIN 33AADCK8845M1ZT")
    doc.add_paragraph("Date: 05/10/2026")
    doc.add_paragraph("To\nMs. Priya Kulkarni\nCategory Manager - Packaging\nDeccan Peak Breweries Ltd., Waluj")
    doc.add_paragraph(f"Sub: Our proposal for your annual corrugated requirement - Ref. {RFX['id']}")
    doc.add_paragraph("Dear Madam,")
    doc.add_paragraph(
        "Thank you for inviting Kaveri Kraftline to participate. We have been supplying breweries and beverage majors across South "
        "India for over fifteen years and are confident of meeting Deccan Peak's quality expectations. Our proposal is set out below. "
        "All prices mentioned in this letter are delivered to your Waluj plant and are inclusive of GST at 18%.")
    doc.add_heading("Bottle and can shippers", level=2)
    doc.add_paragraph(
        f"For the 650 ml x 12 shippers for Classic Lager and Strong, we propose our standard 5-ply construction with a 120 GSM / 18 BF top "
        f"liner, which in our experience gives fully adequate stacking performance at a better price point, at {r('L01')} and {r('L02')} per box "
        f"respectively. The premium Peak Wheat 650 ml shipper will be made exactly to your 180/24BF specification with 4-colour printing at "
        f"{r('L03')} per box. The 330 ml x 24 bottle shipper is offered at {r('L04')}. For cans, the 330 ml x 24 Classic shipper and the "
        f"500 ml x 24 Strong shipper are offered in the same economical 120/18BF top construction at {r('L05')} and {r('L06')} per box, and the "
        f"premium 500 ml can shipper to your specification at {r('L07')}. Plain shippers for contract bottling will be {r('L08')} (650 ml) and "
        f"{r('L09')} (330 ml cans). The keg collar sleeve is {r('L24')}, the IPL limited-edition promo shipper {r('L25')}, and the 6 x 650 ml QA "
        f"sample carton {r('L26')}.")
    doc.add_heading("Master cartons, outers and spares", level=2)
    doc.add_paragraph(
        f"Master cartons for 4 x 6-pack cans will be {r('L10')} for 330 ml and {r('L11')} for 500 ml. The gift-pack outer for 2 x 650 ml works out "
        f"to {r('L12')}. General-purpose spares cartons are {r('L13')} for the small size and {r('L14')} for the large size.")
    doc.add_heading("Trays, partitions and pads", level=2)
    doc.add_paragraph(
        f"Die-cut shrink trays are offered at {r('L15')} (330 ml cans) and {r('L16')} (500 ml cans); the modern-trade display tray at {r('L17')}. "
        f"Partitions for 650 ml bottles are {r('L18')} per pc and for 330 ml bottles {r('L19')} per pc. Layer pads are {r('L20')} for 1000x1200 "
        f"and {r('L21')} for 1100x1100. The top/bottom pad for the 650 ml shipper is {r('L22')}, edge boards {r('L23')} per metre piece, and crate "
        f"liners {r('L27')}.")
    doc.add_paragraph(
        "We regret that we are unable to quote for the 7-ply export shippers and the WR-coated cold-chain shipper at this time, as our "
        "7-ply line is fully booked for the coming season.")
    doc.add_heading("Commercial terms and compliance", level=2)
    qa = QA["C"]
    doc.add_paragraph(
        f"Payment terms requested are 60 days from invoice. Our standard lead time is about 12 days from PO including transit to Waluj, which "
        f"is approximately 1,050 km from our plant. We are ISO 9001:2015 certified and use low-migration inks on all beverage work. Box "
        f"compression and burst testing is carried out for us by the Indian Institute of Packaging, Mumbai on a quarterly basis. Our rejection "
        f"rate over the last twelve months is 1.9%. We can comfortably commit 120% of your peak monthly volume. Paper is sourced from domestic "
        f"mills with recycled content.")
    doc.add_paragraph("We look forward to a long and mutually rewarding association.\n\nYours faithfully,\nFor Kaveri Kraftline Pvt. Ltd.\n\nS. Venkatesh\nGeneral Manager - Marketing")
    doc.save(d / "Kaveri_Kraftline_Proposal_DeccanPeak.docx")
    (d / "email.txt").write_text(
        f"From: {v['contact']} <{v['email']}>\nTo: {BUYER['email']}\nDate: Mon, 5 Oct 2026 11:20 +0530\n"
        f"Subject: Kaveri Kraftline - proposal for {RFX['id']}\nAttachments: Kaveri_Kraftline_Proposal_DeccanPeak.docx\n\n"
        "Respected Madam,\n\nPlease find enclosed our proposal letter. We have given our most competitive pricing and offered value-engineered "
        "board on high-volume items to help you reduce cost.\n\nRegards,\nS. Venkatesh\nKaveri Kraftline Pvt. Ltd.\n")

# =========================== Vendor D: Photo =================================
def render_d():
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    import numpy as np
    v = VENDORS["D"]; d = ROOT / "inbox/vendor_D_godavari"; d.mkdir()
    W, H = 1240, 1700
    rng = np.random.default_rng(7)
    paper = (np.ones((H, W, 3)) * np.array([246, 242, 230]) + rng.normal(0, 4, (H, W, 3))).clip(0, 255).astype("uint8")
    img = Image.fromarray(paper); dr = ImageDraw.Draw(img)
    F = "/usr/share/fonts/truetype/dejavu/"
    fb = ImageFont.truetype(F + "DejaVuSerif-Bold.ttf", 54); fm = ImageFont.truetype(F + "DejaVuSans.ttf", 30)
    fs = ImageFont.truetype(F + "DejaVuSans.ttf", 24); fbig = ImageFont.truetype(F + "DejaVuSansMono-Bold.ttf", 40) if os.path.exists(F + "DejaVuSansMono-Bold.ttf") else ImageFont.truetype(F + "DejaVuSansMono.ttf", 40)
    fh = ImageFont.truetype(F + "DejaVuSansCondensed-Oblique.ttf", 34)
    dr.text((W // 2, 90), "GODAVARI BOX WORKS", font=fb, fill=(20, 40, 110), anchor="mm")
    dr.text((W // 2, 150), "Plot W-77, MIDC Waluj, Aurangabad  *  Mob. 98230 XXXXX", font=fs, fill=(40, 40, 40), anchor="mm")
    dr.text((W // 2, 190), "Mfrs: Corrugated Boxes, Sheets, Partitions, Trays", font=fs, fill=(40, 40, 40), anchor="mm")
    dr.line((80, 230, W - 80, 230), fill=(20, 40, 110), width=4)
    dr.text((W // 2, 290), "RATE CARD  2026-27   (Rs. per Kg)", font=fm, fill=(10, 10, 10), anchor="mm")
    rows = [("3 Ply Plain", D_RATE["3P_PLAIN"]), ("3 Ply Printed", D_RATE["3P_PRINT"]), ("5 Ply Plain", D_RATE["5P_PLAIN"]),
            ("5 Ply Printed (2 col)", "BLUR5"), ("7 Ply", "BLUR7"), ("Die-cut Trays", D_RATE["TRAY"]),
            ("Partitions / Dividers", D_RATE["PARTITION"]), ("Pads / Sheets", D_RATE["PAD"])]
    y0 = 360; rh = 92
    dr.rectangle((110, y0, W - 110, y0 + rh * (len(rows) + 1)), outline=(30, 30, 30), width=3)
    dr.line((760, y0, 760, y0 + rh * (len(rows) + 1)), fill=(30, 30, 30), width=3)
    dr.text((140, y0 + rh // 2), "ITEM", font=fm, fill=(0, 0, 0), anchor="lm"); dr.text((800, y0 + rh // 2), "RATE / KG", font=fm, fill=(0, 0, 0), anchor="lm")
    blur_boxes = []
    for i, (name, val) in enumerate(rows, 1):
        y = y0 + rh * i
        dr.line((110, y, W - 110, y), fill=(30, 30, 30), width=2)
        dr.text((140, y + rh // 2), name, font=fm, fill=(0, 0, 0), anchor="lm")
        if isinstance(val, str):
            key = "5P_PRINT" if val == "BLUR5" else "7P"
            a, b = D_BLUR[key]
            # overlay misread and true value so the photo is genuinely ambiguous
            layer = Image.new("L", (W, H), 0); ld = ImageDraw.Draw(layer)
            ld.text((830, y + rh // 2), f"{a:.2f}", font=fbig, fill=150, anchor="lm"); ld.text((830, y + rh // 2), f"{b:.2f}", font=fbig, fill=150, anchor="lm")
            img.paste((15, 15, 15), (0, 0), layer)
            blur_boxes.append((815, y + 10, 1060, y + 82))
        else:
            dr.text((830, y + rh // 2), f"{val:.2f}", font=fbig, fill=(15, 15, 15), anchor="lm")
    yb = y0 + rh * (len(rows) + 1) + 50
    notes = ["Terms:", "* GST 18% extra", "* Free delivery within MIDC Waluj", "* Box wt. as per party approved spec",
             "* Payment 30 days", "* Rates valid till 31-03-2027"]
    for i, n in enumerate(notes):
        dr.text((120, yb + i * 40), n, font=fs, fill=(30, 30, 30))
    # handwritten additions
    dr.text((640, yb + 10), "4 colour print - extra Rs 1.75/box", font=fh, fill=(20, 50, 160))
    dr.text((640, yb + 60), "WR coating + Rs 2/box", font=fh, fill=(20, 50, 160))
    dr.text((640, yb + 110), "Edge board - not available", font=fh, fill=(20, 50, 160))
    dr.text((640, yb + 170), "For Deccan Peak - A. Jadhav", font=fh, fill=(20, 50, 160))
    for bx in blur_boxes:  # smudge
        reg = img.crop(bx).filter(ImageFilter.GaussianBlur(3.2)); img.paste(reg, bx[:2])
    # coffee ring / fold shadow
    arr = np.array(img).astype(float)
    xs = np.linspace(-1, 1, W)[None, :, None]; arr *= (1 - 0.10 * np.exp(-((xs - 0.05) ** 2) / 0.002))
    img = Image.fromarray(arr.clip(0, 255).astype("uint8"))
    # place on a dark desk, perspective + rotation, lighting gradient
    canvas = Image.new("RGB", (1600, 2000), (58, 44, 34))
    coeffs = _persp((0, 0, W, 0, W, H, 0, H), (170, 150, 1410, 172, 1440, 1835, 120, 1800))
    warped = img.transform((1600, 2000), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    mask = Image.new("L", (W, H), 255).transform((1600, 2000), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    canvas.paste(warped, (0, 0), mask)
    a = np.array(canvas).astype(float)
    gy, gx = np.mgrid[0:2000, 0:1600]
    a *= (0.72 + 0.38 * (gx / 1600) * (1 - gy / 2600))[..., None]
    a += rng.normal(0, 5, a.shape)
    canvas = Image.fromarray(a.clip(0, 255).astype("uint8")).rotate(1.2, resample=Image.BICUBIC, fillcolor=(40, 30, 24))
    canvas = canvas.filter(ImageFilter.GaussianBlur(0.9)).resize((1200, 1500))
    canvas.save(d / "IMG_20261007_WA0012.jpg", quality=62)
    (d / "email.txt").write_text(
        f"From: Godavari Box Works <{v['email']}>\nTo: {BUYER['email']}\nDate: Wed, 7 Oct 2026 21:47 +0530\n"
        f"Subject: rate card\nAttachments: IMG_20261007_WA0012.jpg\n\n"
        "Madam namaskar,\n\nPls find our rate card attached for your enquiry. All items we can supply except edge board. Weight will be as per "
        "your spec sheet. Our factory is only 3 km from your plant so delivery same day / next day possible.\n\n"
        "Your questions -\nISO yes, certificate will send tomorrow\nTesting - we have burst tester, BCT we do at customer end\nInk - food safe yes\n"
        "Rejection - under 2%\nCapacity - no problem, we will increase shift in peak season\nLead time 3-4 days\nFSC - no\n\n"
        "Thanks\nAnil Jadhav\nGodavari Box Works\nSent from my phone\n")

def _persp(src, dst):
    import numpy as np
    m = []
    for (x, y), (X, Y) in zip(zip(dst[0::2], dst[1::2]), zip(src[0::2], src[1::2])):
        m.append([x, y, 1, 0, 0, 0, -X * x, -X * y]); m.append([0, 0, 0, x, y, 1, -Y * x, -Y * y])
    A = np.array(m, dtype=float); B = np.array(src, dtype=float)
    return np.linalg.solve(A, B).tolist()

# ============================== Vendor E: email ==============================
def render_e():
    v = VENDORS["E"]; d = ROOT / "inbox/vendor_E_nordvik"; d.mkdir()
    q = Q["E"]
    (d / "email.txt").write_text(
        f"From: {v['contact']} <{v['email']}>\nTo: {BUYER['email']}\nDate: Wed, 7 Oct 2026 23:58 +0530\n"
        f"Subject: RE: {RFX['id']}\n\n"
        "Hi Priya,\n\n"
        f"Quick one before the deadline - USD {q['L01']['raw_value']:.2f}/pc for the 650 Classic shipper (5-ply), {q['L05']['raw_value']:.2f} for the 330 can x24. "
        "Rest same as last year, freight extra. Can't do the export 7-ply this year.\n\n"
        "Qs: ISO yes (group cert), lab yes, inks yes, rejection was 3.8% last yr - mostly the Feb batch issue you know about, fixed now. "
        "Capacity fine from Bhiwandi + Vapi, lead time 10 days, FSC yes.\n\n"
        "Payment 90 days as usual pls.\n\nCheers,\nKaran\n\n--\nKaran Mehta | Key Account Manager | Nordvik Packaging India Pvt. Ltd.\n"
        "A Nordvik Group company\n")

# ============================== Answer key ===================================
def render_answer_key():
    key = {"generated_note": "Ground truth for accuracy evaluation. Never shown to the extraction or analyst agents.",
           "usd_inr_reference": USD_INR, "vendors": {}, "traps": [], "scenarios": {}}
    for vid, meta in VENDORS.items():
        lines = {}
        for lid, qq in Q[vid].items():
            e = dict(qq); e["landed_inr_per_unit_exgst"] = delivered(vid, lid, qq)
            lines[lid] = e
        missing = [l[0] for l in LINES if l[0] not in Q[vid]]
        key["vendors"][vid] = dict(meta, lines=lines, missing_lines=missing, questionnaire=QA[vid])
    key["traps"] = [
        {"vendor": "A", "type": "unit", "detail": "Rates are per 100 Nos - divide by 100. Own item names/order; must map to RFx lines by size/spec."},
        {"vendor": "B", "type": "hidden_discount", "detail": "4% trade discount in tiny footnote, conditional on annual order > Rs 50 lakh."},
        {"vendor": "B", "type": "freight", "detail": "Ex-works Daman, freight at actuals - estimate with buyer freight benchmark Rs 3.20/kg and flag."},
        {"vendor": "B", "type": "compliance", "detail": "ISO 9001 certificate expired 31-Aug-2026 although questionnaire says 'Yes'."},
        {"vendor": "C", "type": "gst", "detail": "All prices INCLUSIVE of GST 18% - divide by 1.18."},
        {"vendor": "C", "type": "missing_lines", "detail": "No quote for L28, L29, L30 (27 of 30)."},
        {"vendor": "C", "type": "spec_deviation", "detail": "L01, L02, L05, L06 offered on 120/18BF top liner instead of 150/22BF - cheaper, non-compliant."},
        {"vendor": "C", "type": "unit", "detail": "Partitions L18/L19 quoted 'per pc' = per strip; set has 5 / 8 strips. Taken per set it is an ~80% outlier."},
        {"vendor": "C", "type": "compliance", "detail": "Testing outsourced (fails Q2 in-house); lead time 12 days fails Q6."},
        {"vendor": "D", "type": "unit", "detail": "Rates per kg by category; convert with buyer spec weights. Rate card has no line items - map by category."},
        {"vendor": "D", "type": "illegible", "detail": "5-ply printed rate reads as 62.50 or 68.50 (true 68.50). Flips 8 lines worth ~Rs 20 lakh. Must be flagged, not guessed."},
        {"vendor": "D", "type": "illegible", "detail": "7-ply rate reads 64 or 69 (true 64). Low value, does not change any award."},
        {"vendor": "D", "type": "missing_lines", "detail": "Edge board L23 not available."},
        {"vendor": "D", "type": "compliance", "detail": "ISO cert not attached; BCT not in-house; rejection 'under 2%' not numeric."},
        {"vendor": "E", "type": "currency", "detail": "USD pricing, no FX rate stated."},
        {"vendor": "E", "type": "reference", "detail": "'Rest same as last year' - resolvable for 18 lines via buyer_records/fy26_contract_prices.csv (USD, unconfirmed); 8 lines unknowable."},
        {"vendor": "E", "type": "compliance", "detail": "Rejection 3.8% > 2.0% mandatory - fails questionnaire."},
    ]
    with open(ROOT / "answer_key/ground_truth.json", "w") as f:
        json.dump(key, f, indent=2)
    with open(ROOT / "answer_key/ground_truth_landed.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["line_id", "description", "annual_qty"] + [f"{v}_landed" for v in VENDORS])
        for l in LINES:
            w.writerow([l[0], l[1], l[9]] + [delivered(v, l[0], Q[v][l[0]]) if l[0] in Q[v] else "" for v in VENDORS])

if __name__ == "__main__":
    render_rfx(); render_buyer_records(); render_a(); render_b(); render_c(); render_d(); render_e(); render_answer_key()
    for p in sorted(ROOT.rglob("*")):
        if p.is_file():
            print(f"{p.relative_to(ROOT)}  ({p.stat().st_size // 1024} KB)")
