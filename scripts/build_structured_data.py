"""
Turns the two Office-of-Academics spreadsheets into clean CSVs that the
schedule / email tools can query directly.

  data/source_xlsx/finalized_courses_AY2026-27_sem1.xlsx  ->  data/structured/courses.csv
  data/source_xlsx/slot_system_AY2026-27_sem1.xlsx        ->  data/structured/slot_timings.csv
                                                              data/structured/slot_rules.md   (also goes into RAG)
  (instructor names from courses.csv)                     ->  data/structured/faculty_directory.csv  (DUMMY emails)

Every department sent its sheet in its own format (different headers, title rows,
"3 credits" vs 3.0, L-T-P hidden inside the credits column, ...), so most of this
file is header detection and value cleaning.

Run:  python scripts/build_structured_data.py
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from helpdesk.departments import DEPARTMENTS, split_instructors  # noqa: E402
XLSX_DIR = ROOT / "data" / "source_xlsx"
OUT_DIR = ROOT / "data" / "structured"

COURSES_XLSX = XLSX_DIR / "finalized_courses_AY2026-27_sem1.xlsx"
SLOTS_XLSX = XLSX_DIR / "slot_system_AY2026-27_sem1.xlsx"

COURSE_SOURCE = "Finalized Courses List, AY 2026-27 Semester I (Office of Academics)"
SLOT_SOURCE = "Slot System for B.Tech. 2nd year onwards, AY 2026-27 Semester I"

# header keyword -> canonical field. Order matters: first match wins for a column.
HEADER_RULES = [
    ("co_instructor", [r"co-?instructor"]),
    ("code", [r"course\s*code", r"subject\s*code", r"^code$"]),
    ("name", [r"course\s*name", r"course\s*title", r"subject\s*name", r"name of the course"]),
    ("ltp", [r"l-?t-?p"]),
    ("credits", [r"^credits?$"]),
    ("instructor", [r"instructor", r"faculty", r"coordinator"]),
    ("slot", [r"slot"]),
    ("category", [r"categor", r"course\s*type", r"^type$"]),
    ("offered_for", [r"offered for", r"programme", r"program name", r"^batch$", r"^year$"]),
    ("remarks", [r"remark", r"comment"]),
]

CODE_RE = re.compile(r"^([A-Z]{2,4})\s*(\d|X)", re.I)


def clean(v) -> str:
    if v is None:
        return ""
    s = str(v).replace("\n", " ").strip()
    s = re.sub(r"\s+", " ", s)
    if re.fullmatch(r"\d+\.0", s):  # 3.0 -> 3, 1.0 -> 1 (serial numbers, credits)
        s = s[:-2]
    return s


def detect_header(row: list[str]) -> dict[int, str] | None:
    """Return {col_index: field} if this row looks like a header row."""
    mapping: dict[int, str] = {}
    for idx, cell in enumerate(row):
        low = cell.lower()
        if not low:
            continue
        for field, patterns in HEADER_RULES:
            if field in mapping.values() and field not in ("remarks",):
                continue
            if any(re.search(p, low) for p in patterns):
                mapping[idx] = field
                break
    fields = set(mapping.values())
    if "name" in fields and ("code" in fields or "instructor" in fields):
        return mapping
    return None


def parse_credits(credits_raw: str, ltp_raw: str) -> tuple[str, str]:
    """Return (ltp, credits) as clean strings. Handles '3 credits', '3-0-0 (3)', '3 (3-0-0)'."""
    ltp, credits = "", ""
    for text in (ltp_raw, credits_raw):
        m = re.search(r"(\d+)\s*-\s*(\d+)\s*-\s*(\d+)", text)
        if m and not ltp:
            ltp = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    for text in (ltp_raw, credits_raw):  # "3-0-0 (3)", "0-0-6 (3)"
        m = re.search(r"\d+\s*-\s*\d+\s*-\s*\d+\s*\((\d+(?:\.\d+)?)\)", text)
        if m and not credits:
            credits = m.group(1)
    if not credits:
        m = re.match(r"^\s*(\d+(?:\.\d+)?)", credits_raw)  # "3 credits", "4.5", "3 (3-0-0)"
        if m:
            credits = m.group(1)
    if not credits and ltp:  # derive from L-T-P: L + T + P/2
        l, t, p = (int(x) for x in ltp.split("-"))
        val = l + t + p / 2
        credits = str(int(val)) if val == int(val) else str(val)
    if credits.endswith(".0"):
        credits = credits[:-2]
    return ltp, credits


def course_level(code: str) -> str:
    m = re.match(r"^[A-Z]{2,4}\s*(\d)", code.upper())
    return f"{m.group(1)}00" if m else ""


def build_courses() -> list[dict]:
    wb = openpyxl.load_workbook(COURSES_XLSX, data_only=True)
    out: list[dict] = []
    for ws in wb.worksheets:
        dept_name, _ = DEPARTMENTS.get(ws.title, (ws.title, []))
        mapping = None
        section = ""
        for row_idx, raw in enumerate(ws.iter_rows(values_only=True), start=1):
            row = [clean(c) for c in raw]
            if not any(row):
                continue
            hdr = detect_header(row)
            if hdr:
                mapping = hdr
                continue
            non_empty = [c for c in row if c]
            if len(non_empty) == 1 and mapping is None or (len(non_empty) == 1 and not CODE_RE.match(non_empty[0])):
                section = non_empty[0]  # e.g. "UG Semester-1", "PG Semester-1 ( DADT)"
                continue
            if mapping is None:
                continue
            rec = {f: "" for f in ("code", "name", "ltp", "credits", "instructor", "co_instructor",
                                   "slot", "category", "offered_for", "remarks")}
            for idx, field in mapping.items():
                if idx < len(row) and row[idx]:
                    rec[field] = (rec[field] + "; " + row[idx]).strip("; ") if rec[field] else row[idx]
            # trailing un-headed cells (e.g. CSE "Drop CST8010 and register in CST7010")
            extra = [row[i] for i in range(len(row)) if i not in mapping and row[i]]
            if extra and not re.fullmatch(r"[\d.]+", extra[0]):
                rec["remarks"] = "; ".join(x for x in [rec["remarks"], *extra] if x)
            if not rec["name"]:
                continue
            ltp, credits = parse_credits(rec["credits"], rec["ltp"])
            code = rec["code"].replace(" ", "").upper()
            out.append({
                "course_code": code,
                "course_name": rec["name"],
                "department": dept_name,
                "dept_sheet": ws.title,
                "level": course_level(code),
                "ltp": ltp or rec["ltp"],
                "credits": credits,
                "instructor": rec["instructor"].replace("**", "").strip(),
                "co_instructors": rec["co_instructor"].strip("- "),
                "slot": rec["slot"],
                "category": rec["category"],
                "offered_for": "; ".join(x for x in [rec["offered_for"], section] if x),
                "remarks": rec["remarks"],
                "source": f"{COURSE_SOURCE}, sheet '{ws.title}', row {row_idx}",
            })
    return out


# ----------------------------------------------------------------------------------------
# Slot system
# ----------------------------------------------------------------------------------------
DAY_COLS = {"Mon": (2, 3), "Tue": (4, 5), "Wed": (6, 7), "Thu": (8, 9), "Fri": (10, 11)}  # (theory col, lab col), 1-based


def _time_range(label: str) -> tuple[str, str]:
    """'9– 9:50' -> ('09:00','09:50');  '1–1:50' -> ('13:00','13:50')"""
    parts = re.split(r"\s*[–-]\s*", label.strip())
    def norm(t: str) -> tuple[int, int]:
        h, _, m = t.strip().partition(":")
        h, m = int(h), int(m or 0)
        if h < 8:  # 1..6 pm
            h += 12
        return h, m
    (h1, m1), (h2, m2) = norm(parts[0]), norm(parts[1])
    return f"{h1:02d}:{m1:02d}", f"{h2:02d}:{m2:02d}"


def build_slots() -> tuple[list[dict], str]:
    wb = openpyxl.load_workbook(SLOTS_XLSX, data_only=True)
    ws = wb.active
    merged_end = {}
    for rng in ws.merged_cells.ranges:  # lab slots span two rows (2 hours)
        merged_end[(rng.min_row, rng.min_col)] = rng.max_row

    rows: list[dict] = []
    for r in range(3, 14):
        label = clean(ws.cell(r, 1).value)
        if not label:
            continue
        start, end = _time_range(label)
        for day, (tcol, lcol) in DAY_COLS.items():
            theory = clean(ws.cell(r, tcol).value)
            if theory and len(theory) <= 3:
                rows.append({"slot": theory.upper(), "day": day, "start": start, "end": end,
                             "kind": "lecture/tutorial", "source": SLOT_SOURCE})
            lab = clean(ws.cell(r, lcol).value)
            if lab and len(lab) <= 3:
                last = merged_end.get((r, lcol), r)
                _, lab_end = _time_range(clean(ws.cell(last, 1).value))
                rows.append({"slot": lab.upper(), "day": day, "start": start, "end": lab_end,
                             "kind": "lab (2 h)", "source": SLOT_SOURCE})

    # Text part of the sheet (notes + programme-wise slot allocation) -> markdown for RAG
    notes = []
    for col, day in ((2, "Monday"), (4, "Tuesday"), (6, "Wednesday"), (8, "Thursday")):  # 5 pm row
        t = clean(ws.cell(12, col).value)
        if t:
            notes.append(f"- {day} 5:00-5:50 pm: {t}")
    for r in range(14, 22):
        txt = clean(ws.cell(r, 2).value)
        if txt and len(txt) > 25:
            notes.append(f"- {txt}")
    alloc = []
    for r in range(24, 35):
        prog = clean(ws.cell(r, 1).value)
        comp = clean(ws.cell(r, 6).value)
        elec = clean(ws.cell(r, 9).value)
        if prog:
            alloc.append(f"| {prog} | {comp or '-'} | {elec or '-'} |")
    lab_alloc = []
    for r in range(3, 17):
        b, roll, lab, slot = (clean(ws.cell(r, c).value) for c in (13, 14, 15, 16))
        if b and lab:
            lab_alloc.append(f"| {b} | {roll} | {lab} | {slot} |")
    abbrev = [clean(ws.cell(r, 13).value) for r in range(20, 28) if clean(ws.cell(r, 13).value)]

    md = [
        f"# {SLOT_SOURCE}",
        "",
        "Source: Office of Academics spreadsheet 'AY 2026-27_Semester I_Slot System 2nd Year onwards'.",
        "",
        "## Weekly slot grid (Monday to Friday)",
        "",
        "| Time | Mon | Tue | Wed | Thu | Fri |",
        "|---|---|---|---|---|---|",
    ]
    for r in range(3, 12):
        label = clean(ws.cell(r, 1).value)
        cells = []
        for day, (tcol, lcol) in DAY_COLS.items():
            t, l = clean(ws.cell(r, tcol).value), clean(ws.cell(r, lcol).value)
            cells.append(" / ".join(x for x in (t, l) if x) or "-")
        md.append(f"| {label} | " + " | ".join(cells) + " |")
    md += [
        "",
        "Lab slots L1-L10 and M1-M10 are two hours long (for example L1 is Monday 9:00-10:50 and M1 is Monday 1:00-2:50 pm).",
        "Friday 5:00-5:50 pm is slot N. 6:00-6:50 pm on all days is reserved for tutorials.",
        "",
        "## Notes and rules",
        "",
        *notes,
        "",
        "## Programme-wise slot allocation for courses with a theory component",
        "",
        "| Programme / course level | Compulsory course slots | Elective course slots |",
        "|---|---|---|",
        *alloc,
        "",
        "## Schedule of DSA and IML labs for UG 2nd-year students",
        "",
        "| Branch | Roll numbers | Lab | Slot |",
        "|---|---|---|---|",
        *lab_alloc,
        "",
        "Abbreviations: " + "; ".join(a for a in abbrev if a.lower() != "abbreviation"),
        "",
    ]
    return rows, "\n".join(md)


# ----------------------------------------------------------------------------------------
# Dummy faculty directory (the real IDs are personal data, so they are replaced)
# ----------------------------------------------------------------------------------------
def dummy_email(name: str, taken: set[str]) -> str:
    slug = re.sub(r"[^a-z ]", "", name.lower()).split()
    local = f"{slug[0]}.{slug[-1]}" if len(slug) > 1 else slug[0]
    candidate, n = local, 2
    while candidate in taken:
        candidate, n = f"{local}{n}", n + 1
    taken.add(candidate)
    return f"{candidate}@iitj-dummy.ac.in"


def build_faculty(courses: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    taken: set[str] = set()
    for c in courses:
        for field in (c["instructor"], c["co_instructors"]):
            for n in split_instructors(field):
                key = n.lower()
                if key not in seen:
                    seen[key] = {"name": n, "email": dummy_email(n, taken), "department": c["department"],
                                 "note": "DUMMY e-mail generated for this project; real IDs were replaced"}
    return sorted(seen.values(), key=lambda r: r["name"].lower())


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    courses = build_courses()
    write_csv(OUT_DIR / "courses.csv", courses)
    slots, slot_md = build_slots()
    write_csv(OUT_DIR / "slot_timings.csv", slots)
    (ROOT / "data" / "raw" / "slot_system_rules_AY2026-27_sem1.md").write_text(slot_md, encoding="utf-8")
    faculty = build_faculty(courses)
    write_csv(OUT_DIR / "faculty_directory.csv", faculty)
    print(f"courses: {len(courses)} rows | slot timings: {len(slots)} rows | faculty: {len(faculty)} people")


if __name__ == "__main__":
    sys.exit(main())
