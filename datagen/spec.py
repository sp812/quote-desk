"""Single source of truth for the fabricated RFx dataset.

Every vendor file and the answer key are rendered from these tables, so the
ground truth is always consistent with what the vendor documents say.
All companies here are fictional.
"""

BUYER = {
    "name": "Deccan Peak Breweries Ltd.",
    "plant": "Waluj Brewery, Plot B-14, MIDC Waluj, Chhatrapati Sambhajinagar (Aurangabad) 431136, Maharashtra",
    "buyer": "Priya Kulkarni, Category Manager - Packaging",
    "email": "priya.kulkarni@deccanpeak.example",
    "gstin": "27AABCD1234F1Z5",
}

RFX = {
    "id": "RFQ-DPB-PKG-2026-014",
    "title": "Annual Rate Contract - Corrugated Packaging, FY2026-27 (Waluj Brewery)",
    "issued": "2026-09-28",
    "due": "2026-10-07",
    "contract_period": "01-Nov-2026 to 31-Oct-2027",
    "currency": "INR",
    "price_basis": "Per piece (per set for partitions), FOR Waluj plant, exclusive of GST",
    "payment_terms_requested": "45 days from GRN",
    "freight": "Included (FOR destination)",
}

# category -> market "fair" conversion price in INR per kg (FOR Waluj, ex-GST)
CAT_RATE = {
    "3P_PLAIN": 57.0,
    "3P_PRINT": 60.0,
    "5P_PLAIN": 59.0,
    "5P_PRINT": 65.0,
    "7P": 66.0,
    "TRAY": 67.0,
    "PARTITION": 55.0,
    "PAD": 53.0,
}
FOUR_COLOUR_ADDER = 1.60  # INR per piece

# id, description, style, ply, dims (mm), flute, board spec, print, kg/pc, annual qty, category, unit
LINES = [
    ("L01", "Shipper 650 ml x 12 bottles - Deccan Classic Lager", "RSC", 5, "375x285x300", "BC", "150/22BF top, 120/18BF inner", "2-col flexo", 0.580, 220000, "5P_PRINT", "pc"),
    ("L02", "Shipper 650 ml x 12 bottles - Deccan Strong", "RSC", 5, "375x285x300", "BC", "150/22BF top, 120/18BF inner", "2-col flexo", 0.580, 180000, "5P_PRINT", "pc"),
    ("L03", "Shipper 650 ml x 12 bottles - Peak Wheat (premium)", "RSC", 5, "375x285x300", "BC", "180/24BF top, 120/18BF inner", "4-col flexo", 0.610, 30000, "5P_PRINT", "pc"),
    ("L04", "Shipper 330 ml x 24 bottles - Deccan Classic", "RSC", 5, "410x275x235", "BC", "150/22BF top, 120/18BF inner", "2-col flexo", 0.550, 60000, "5P_PRINT", "pc"),
    ("L05", "Shipper 330 ml x 24 cans - Deccan Classic", "RSC", 5, "400x270x125", "BC", "150/22BF top, 120/18BF inner", "2-col flexo", 0.380, 150000, "5P_PRINT", "pc"),
    ("L06", "Shipper 500 ml x 24 cans - Deccan Strong", "RSC", 5, "400x270x170", "BC", "150/22BF top, 120/18BF inner", "2-col flexo", 0.440, 90000, "5P_PRINT", "pc"),
    ("L07", "Shipper 500 ml x 24 cans - Peak Wheat (premium)", "RSC", 5, "400x270x170", "BC", "180/24BF top, 120/18BF inner", "4-col flexo", 0.460, 20000, "5P_PRINT", "pc"),
    ("L08", "Shipper 650 ml x 12 - plain (contract bottling)", "RSC", 5, "375x285x300", "BC", "140/20BF top, 120/18BF inner", "Plain", 0.560, 40000, "5P_PLAIN", "pc"),
    ("L09", "Shipper 330 ml x 24 cans - plain", "RSC", 5, "400x270x125", "BC", "140/20BF top, 120/18BF inner", "Plain", 0.370, 30000, "5P_PLAIN", "pc"),
    ("L10", "Master carton 4 x 6-pack cans 330 ml", "RSC", 3, "395x265x130", "B", "150/20BF", "1-col flexo", 0.240, 50000, "3P_PRINT", "pc"),
    ("L11", "Master carton 4 x 6-pack cans 500 ml", "RSC", 3, "395x265x175", "B", "150/20BF", "1-col flexo", 0.280, 30000, "3P_PRINT", "pc"),
    ("L12", "Mono carton outer - gift pack 2 x 650 ml", "RSC", 3, "200x100x300", "E", "180/22BF", "1-col flexo", 0.150, 15000, "3P_PRINT", "pc"),
    ("L13", "Spares carton - general purpose (small)", "RSC", 3, "300x200x200", "B", "120/18BF", "Plain", 0.180, 8000, "3P_PLAIN", "pc"),
    ("L14", "Spares carton - general purpose (large)", "RSC", 3, "500x400x400", "B", "120/18BF", "Plain", 0.480, 4000, "3P_PLAIN", "pc"),
    ("L15", "Die-cut tray 24 cans 330 ml, shrink-wrap base", "Die-cut tray", 3, "400x270x40", "E", "180/22BF", "Plain", 0.150, 110000, "TRAY", "pc"),
    ("L16", "Die-cut tray 24 cans 500 ml, shrink-wrap base", "Die-cut tray", 3, "400x270x50", "E", "180/22BF", "Plain", 0.160, 70000, "TRAY", "pc"),
    ("L17", "Die-cut display tray 12 x 650 ml (modern trade)", "Die-cut tray", 5, "380x290x120", "BE", "180/24BF top", "2-col flexo", 0.330, 15000, "TRAY", "pc"),
    ("L18", "Partition set 12-cell for 650 ml bottles (2 long + 3 short)", "Slotted partition", 3, "set of 5 strips", "B", "120/18BF", "Plain", 0.120, 150000, "PARTITION", "set"),
    ("L19", "Partition set 24-cell for 330 ml bottles (3 long + 5 short)", "Slotted partition", 3, "set of 8 strips", "B", "120/18BF", "Plain", 0.140, 60000, "PARTITION", "set"),
    ("L20", "Layer pad 1000x1200 mm (pallet tier sheet)", "Pad", 3, "1000x1200", "B", "120/18BF", "Plain", 0.420, 25000, "PAD", "pc"),
    ("L21", "Layer pad 1100x1100 mm (export pallet)", "Pad", 3, "1100x1100", "B", "120/18BF", "Plain", 0.390, 8000, "PAD", "pc"),
    ("L22", "Top/bottom pad for 650 ml shipper", "Pad", 3, "370x280", "B", "120/18BF", "Plain", 0.035, 100000, "PAD", "pc"),
    ("L23", "Corner edge board 50x50x5 mm, 1000 mm", "Edge board", 0, "50x50x5x1000", "-", "Laminated kraft", "Plain", 0.200, 20000, "PAD", "pc"),
    ("L24", "Keg collar sleeve 30 L keg", "RSC sleeve", 5, "420x420x200", "BC", "150/22BF top", "1-col flexo", 0.520, 6000, "5P_PRINT", "pc"),
    ("L25", "Promo shipper 650 ml x 12 - IPL season limited edition", "RSC", 5, "375x285x300", "BC", "180/24BF top, 120/18BF inner", "4-col flexo", 0.610, 25000, "5P_PRINT", "pc"),
    ("L26", "Sample/QA carton 6 x 650 ml", "RSC", 5, "250x190x300", "BC", "150/22BF top", "Plain", 0.330, 5000, "5P_PLAIN", "pc"),
    ("L27", "Glass bottle return crate liner", "Pad", 3, "560x380", "B", "120/18BF", "Plain", 0.090, 30000, "PAD", "pc"),
    ("L28", "Export shipper 650 ml x 12 - 7-ply (Nepal/Bhutan)", "RSC", 7, "380x290x305", "BCB", "180/24BF top, 150/22BF inner", "2-col flexo", 0.850, 12000, "7P", "pc"),
    ("L29", "Export shipper 330 ml x 24 cans - 7-ply", "RSC", 7, "405x275x130", "BCB", "180/24BF top, 150/22BF inner", "2-col flexo", 0.560, 10000, "7P", "pc"),
    ("L30", "Cold-chain shipper 650 ml x 12 - wax/WR coated", "RSC", 5, "375x285x300", "BC", "150/22BF top WR coated, 120/18BF inner", "2-col flexo", 0.620, 20000, "7P", "pc"),
]

# Per-line deterministic "noise" so vendors are not all perfectly proportional.
def noise(vendor: str, line_id: str, spread: float = 0.035) -> float:
    import hashlib
    h = int(hashlib.sha256(f"{vendor}:{line_id}".encode()).hexdigest()[:8], 16)
    return 1.0 + spread * ((h / 0xFFFFFFFF) * 2 - 1)


def fair_price(line) -> float:
    lid, desc, style, ply, dims, flute, board, prn, kg, qty, cat, unit = line
    p = kg * CAT_RATE[cat]
    if "4-col" in prn:
        p += FOUR_COLOUR_ADDER
    return p


QUESTIONNAIRE = [
    ("Q1", "Is your manufacturing plant ISO 9001 certified? Attach a valid certificate.", "Mandatory", "Yes, with certificate valid on the contract start date"),
    ("Q2", "Do you have an in-house testing lab for BCT/ECT/burst strength?", "Mandatory", "Yes, in-house"),
    ("Q3", "Do you use low-migration / food-safe printing inks?", "Mandatory", "Yes"),
    ("Q4", "Rejection rate (%) on supplies over the last 12 months?", "Mandatory", "<= 2.0%"),
    ("Q5", "Can you commit capacity of at least 120% of our monthly peak (Mar-May) volume?", "Mandatory", "Yes"),
    ("Q6", "Standard lead time from PO to delivery at Waluj (days)?", "Mandatory", "<= 10 days"),
    ("Q7", "Is your paper FSC-certified or from certified recycled fibre?", "Preferred", "Yes"),
    ("Q8", "Distance of your manufacturing plant from Waluj (km)?", "Info", "-"),
]

FREIGHT_BENCHMARK_INR_PER_KG = {  # buyer's logistics rate card (part-truck, FY26)
    "Daman -> Waluj": 3.20,
    "Bhiwandi -> Waluj": 2.40,
    "Hosur -> Waluj": 4.60,
    "Chakan -> Waluj": 2.10,
    "Waluj -> Waluj (local)": 0.40,
}

USD_INR = 88.40  # reference rate the system should flag as an assumption
