"""Vendor pricing behaviour and ground truth. All vendors are fictional."""
from spec import LINES, fair_price, noise, FREIGHT_BENCHMARK_INR_PER_KG as FB, USD_INR, FOUR_COLOUR_ADDER

LINE_BY_ID = {l[0]: l for l in LINES}

VENDORS = {
    "A": dict(name="Indrayani Corrupack Pvt. Ltd.", city="Chakan, Pune", format="xlsx",
              contact="Rahul Deshmukh", email="sales@indrayanicorrupack.example",
              payment_days=45, lead_days=7, lane=None),
    "B": dict(name="Seabreeze Packaging Industries", city="Daman", format="pdf",
              contact="Mehul Shah", email="mehul@seabreezepack.example",
              payment_days=30, lead_days=9, lane="Daman -> Waluj"),
    "C": dict(name="Kaveri Kraftline Pvt. Ltd.", city="Hosur, Tamil Nadu", format="docx",
              contact="S. Venkatesh", email="venkatesh@kaverikraftline.example",
              payment_days=60, lead_days=12, lane=None),
    "D": dict(name="Godavari Box Works", city="MIDC Waluj, Aurangabad", format="jpg",
              contact="Anil Jadhav", email="godavariboxworks@gmail.example",
              payment_days=30, lead_days=4, lane=None),
    "E": dict(name="Nordvik Packaging India Pvt. Ltd.", city="Bhiwandi, Thane", format="email",
              contact="Karan Mehta", email="karan.mehta@nordvik-pack.example",
              payment_days=90, lead_days=10, lane="Bhiwandi -> Waluj"),
}

# ---------------- Vendor A: Excel, rates per 100 nos, FOR Waluj, ex-GST -------------
def vendor_a():
    out = {}
    for l in LINES:
        p = round(fair_price(l) * 1.00 * noise("A", l[0]), 2)
        out[l[0]] = dict(raw_value=round(p * 100, 0), raw_unit="INR per 100 nos", per_unit_exgst=round(p * 100, 0) / 100,
                         freight="included", gst="extra")
    return out

# ---------------- Vendor B: PDF, per piece ex-works Daman, 4% discount footnote ----
B_DISCOUNT = 0.04
B_DISCOUNT_THRESHOLD_INR = 5_000_000  # annual order value
def vendor_b():
    out = {}
    for l in LINES:
        exw = round(fair_price(l) * 0.98 * noise("B", l[0]), 2)
        out[l[0]] = dict(raw_value=exw, raw_unit="INR per pc, ex-works Daman", per_unit_exgst=exw,
                         freight="at actuals", gst="extra")
    return out

# ---------------- Vendor C: Word, delivered, GST-inclusive, 27/30, spec downgrades --
C_MISSING = ["L28", "L29", "L30"]
C_DOWNGRADE = {"L01": "120/18BF top", "L02": "120/18BF top", "L05": "120/18BF top", "L06": "120/18BF top"}
C_PER_STRIP = {"L18": 5, "L19": 8}
def vendor_c():
    out = {}
    for l in LINES:
        if l[0] in C_MISSING:
            continue
        p = fair_price(l) * 0.97 * noise("C", l[0])
        if l[0] in C_DOWNGRADE:
            p *= 0.88
        p = round(p, 2)
        incl = round(p * 1.18, 2)
        if l[0] in C_PER_STRIP:
            strips = C_PER_STRIP[l[0]]
            per_strip_incl = round(incl / strips, 2)
            out[l[0]] = dict(raw_value=per_strip_incl, raw_unit="INR per pc (strip), incl. GST 18%",
                             per_unit_exgst=round(per_strip_incl * strips / 1.18, 2), freight="included", gst="included",
                             trap=f"Quoted per strip; one set = {strips} strips")
        else:
            out[l[0]] = dict(raw_value=incl, raw_unit="INR per box, incl. GST 18%", per_unit_exgst=round(incl / 1.18, 2),
                             freight="included", gst="included")
        if l[0] in C_DOWNGRADE:
            out[l[0]]["spec_deviation"] = f"Offered board {C_DOWNGRADE[l[0]]} vs specified {l[6]}"
    return out

# ---------------- Vendor D: photo of rate card, INR/kg, local -----------------------
D_RATE = {"3P_PLAIN": 56.0, "3P_PRINT": 59.5, "5P_PLAIN": 58.5, "5P_PRINT": 68.5, "7P": 64.0,
          "TRAY": 69.0, "PARTITION": 54.0, "PAD": 52.0}
D_BLUR = {"5P_PRINT": (62.5, 68.5), "7P": (64.0, 69.0)}  # (misread, true) - both look plausible on the photo
D_FOUR_COL = 1.75
D_WR_COAT = 2.00
D_NOT_SUPPLIED = ["L23"]  # no edge boards
def vendor_d(rate_5p=None):
    rates = dict(D_RATE)
    if rate_5p is not None:
        rates["5P_PRINT"] = rate_5p
    out = {}
    for l in LINES:
        if l[0] in D_NOT_SUPPLIED:
            continue
        lid, desc, style, ply, dims, flute, board, prn, kg, qty, cat, unit = l
        p = kg * rates[cat]
        if "4-col" in prn:
            p += D_FOUR_COL
        if "WR" in board:
            p += D_WR_COAT
        out[lid] = dict(raw_value=rates[cat], raw_unit=f"INR per kg ({cat})", per_unit_exgst=round(p, 2),
                        freight="free within MIDC Waluj", gst="extra",
                        assumption=f"Converted with buyer-spec box weight {kg} kg")
    return out

# ---------------- Vendor E: email, USD, 'rest same as last year' --------------------
E_EXPLICIT = ["L01", "L05"]
E_LASTYEAR_LINES = ["L02", "L03", "L04", "L06", "L07", "L08", "L09", "L10", "L11", "L15",
                    "L16", "L18", "L19", "L20", "L22", "L24", "L25", "L27"]
FY26_USD_INR = 83.90
def e_usd(lid):
    f = 0.955 if lid in E_EXPLICIT else 1.04  # sharpened the two headline lines only
    return round(fair_price(LINE_BY_ID[lid]) * f * noise("E", lid) / USD_INR, 3)
def vendor_e():
    out = {}
    for lid in E_EXPLICIT:
        usd = round(e_usd(lid), 2)
        out[lid] = dict(raw_value=usd, raw_unit="USD per pc", per_unit_exgst=round(usd * USD_INR, 2),
                        freight="extra", gst="extra", fx_assumption=USD_INR)
    for lid in E_LASTYEAR_LINES:
        usd = round(e_usd(lid), 3)
        out[lid] = dict(raw_value=usd, raw_unit="USD per pc (FY26 contract, 'same as last year')",
                        per_unit_exgst=round(usd * USD_INR, 2), freight="extra", gst="extra",
                        fx_assumption=USD_INR, confirmed=False)
    return out

def delivered(vendor, lid, q, apply_b_discount=True):
    """True landed ex-GST INR per unit."""
    kg = LINE_BY_ID[lid][8]
    p = q["per_unit_exgst"]
    if vendor == "B":
        if apply_b_discount:
            p *= (1 - B_DISCOUNT)
        p += FB["Daman -> Waluj"] * kg
    if vendor == "E":
        p += FB["Bhiwandi -> Waluj"] * kg
    return round(p, 2)

# Questionnaire answers (ground truth)
QA = {
    "A": {"Q1": "Yes - cert attached (valid to 2028)", "Q2": "Yes, in-house BCT & burst tester", "Q3": "Yes", "Q4": "1.1%",
          "Q5": "Yes", "Q6": "7 days", "Q7": "Recycled fibre, no FSC", "Q8": "245 km", "verdict": "PASS"},
    "B": {"Q1": "Yes - cert attached", "Q2": "Yes", "Q3": "Yes", "Q4": "1.6%", "Q5": "Yes", "Q6": "9 days",
          "Q7": "FSC Mix certified", "Q8": "410 km", "verdict": "FLAG",
          "issue": "ISO 9001 certificate attached EXPIRED on 31-Aug-2026 - before contract start"},
    "C": {"Q1": "Yes", "Q2": "Testing done at IIP Mumbai (outsourced), not in-house", "Q3": "Yes", "Q4": "1.9%",
          "Q5": "Yes", "Q6": "12 days", "Q7": "Not specified", "Q8": "approx. 1,050 km", "verdict": "FAIL",
          "issue": "Q2 lab is outsourced; Q6 lead time 12 days > 10"},
    "D": {"Q1": "Yes (cert to be sent)", "Q2": "Yes - burst tester only, BCT via customer", "Q3": "Yes", "Q4": "under 2%",
          "Q5": "Yes", "Q6": "3-4 days", "Q7": "No", "Q8": "3 km", "verdict": "FLAG",
          "issue": "ISO cert not attached; 'burst tester only' is partial on Q2; Q4 not a number"},
    "E": {"Q1": "Yes (group certification)", "Q2": "Yes", "Q3": "Yes", "Q4": "3.8%", "Q5": "Yes, from Bhiwandi + Vapi",
          "Q6": "10 days", "Q7": "FSC certified", "Q8": "approx. 330 km", "verdict": "FAIL", "issue": "Q4 rejection 3.8% > 2.0%"},
}

ALL = {"A": vendor_a, "B": vendor_b, "C": vendor_c, "D": vendor_d, "E": vendor_e}
