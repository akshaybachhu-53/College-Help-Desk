"""Tools the agents can call. Every tool returns a dict with a `source` field so the
answer can cite where the information came from.

  search_academic_documents  - hybrid RAG search over regulations, calendar, curriculum, fees ...
  lookup_course              - one course by code or name (slot, instructor, credits ...)
  list_courses               - filter/count courses (department, level, category, slot)
  get_slot_timings           - days and times of a slot (A..V, L1..L10, M1..M10)
  get_instructor_contact     - instructor name + (dummy) e-mail for a course
  save_email_draft           - write an e-mail draft for the student to review (never sent)
  log_unanswered_question    - record a question the helpdesk could not answer
"""
from __future__ import annotations

import csv
import difflib
import json
import re
from datetime import datetime
from functools import lru_cache

from helpdesk import config
from helpdesk.departments import DEPARTMENTS, split_instructors

COURSE_SRC = "Finalized Courses List AY 2026-27 Semester I"
SLOT_SRC = "Slot System AY 2026-27 Semester I"
FACULTY_SRC = "Faculty Directory (dummy e-mail IDs)"


# ------------------------------------------------------------------ data loading
@lru_cache(maxsize=1)
def _courses() -> list[dict]:
    with (config.STRUCTURED_DIR / "courses.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def _slots() -> list[dict]:
    with (config.STRUCTURED_DIR / "slot_timings.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def _faculty() -> dict[str, dict]:
    with (config.STRUCTURED_DIR / "faculty_directory.csv").open(encoding="utf-8") as f:
        return {r["name"].lower(): r for r in csv.DictReader(f)}


def _norm_code(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def _public(c: dict) -> dict:
    keep = ("course_code", "course_name", "department", "level", "ltp", "credits", "instructor",
            "co_instructors", "slot", "category", "offered_for", "remarks")
    return {k: c[k] for k in keep if c.get(k)}


def _resolve_department(dept: str) -> list[str]:
    d = dept.strip().lower()
    if not d:
        return []
    hits = [sheet for sheet, (name, aliases) in DEPARTMENTS.items()
            if d == sheet.lower() or d in aliases or d in name.lower()]
    if not hits:  # "Humanities department", "dept of mechanical"
        hits = [sheet for sheet, (name, aliases) in DEPARTMENTS.items()
                if any(re.search(rf"\b{re.escape(a)}\b", d) for a in aliases if len(a) > 2)]
    return hits


def _find_courses(query: str) -> list[dict]:
    q = query.strip()
    code = _norm_code(q)
    exact = [c for c in _courses() if c["course_code"] and _norm_code(c["course_code"]) == code]
    if exact:
        return exact
    m = re.search(r"\b([A-Z]{3}\d{4,5})\b", q.upper())  # code inside a longer string
    if m:
        exact = [c for c in _courses() if _norm_code(c["course_code"]) == m.group(1)]
        if exact:
            return exact
        return []  # a well-formed code that is not floated: do NOT fall back to name matching
    ql = q.lower()
    contains = [c for c in _courses() if ql in c["course_name"].lower()]
    if contains:  # exact title first, then shortest title ("Fluid Mechanics" before "Advanced Solid and Fluid Mechanics")
        return sorted(contains, key=lambda c: (c["course_name"].lower() != ql, len(c["course_name"])))
    names = list({c["course_name"].lower() for c in _courses()})
    close = difflib.get_close_matches(ql, names, n=3, cutoff=0.75)
    return [c for c in _courses() if c["course_name"].lower() in close]


# ------------------------------------------------------------------ tools
def lookup_course(course: str) -> dict:
    """Look up a course floated in AY 2026-27 Semester I by course code (e.g. "CSL7650") or by
    course name (e.g. "Autonomous Systems"). Returns slot, instructor, credits, L-T-P and department.

    Args:
        course: course code or (part of) the course name.
    """
    hits = _find_courses(course)
    if not hits:
        return {"found": False, "query": course, "source": COURSE_SRC,
                "message": f"No course matching '{course}' is in the AY 2026-27 Semester I course list."}
    return {"found": True, "matches": [_public(c) for c in hits[:8]], "total_matches": len(hits),
            "source": COURSE_SRC}


def list_courses(department: str = "", level: str = "", category: str = "", slot: str = "") -> dict:
    """List and COUNT courses floated this semester, filtered by department, course level,
    category and/or slot. Use this for "how many ... courses/electives ..." questions.

    Args:
        department: department name or short form, e.g. "Humanities", "Mechanical", "CSE". Empty = all.
        level: course level such as "400" or "700" (first digit of the code). Empty = all.
        category: text to match in the category column, e.g. "PE" (programme elective), "PC", "OE". Empty = all.
        slot: slot letter such as "K". Empty = all.
    """
    rows = _courses()
    applied = {}
    if department:
        sheets = _resolve_department(department)
        if not sheets:
            return {"found": False, "message": f"Unknown department '{department}'.",
                    "known_departments": [v[0] for v in DEPARTMENTS.values()], "source": COURSE_SRC}
        rows = [r for r in rows if r["dept_sheet"] in sheets]
        applied["department"] = ", ".join(DEPARTMENTS[s][0] for s in sheets)
    if level:
        lv = re.sub(r"\D", "", level)[:1]
        rows = [r for r in rows if r["level"].startswith(lv)]
        applied["level"] = f"{lv}00"
    fallback_note = ""
    if category:
        cat = category.strip().lower()
        matched = [r for r in rows if re.search(rf"\b{re.escape(cat)}\b",
                                                (r["category"] + " " + r["offered_for"] + " " + r["remarks"]).lower())]
        if matched:
            rows = matched
            applied["category"] = category
        else:  # many departments leave the category column blank (e.g. SoLA electives)
            fallback_note = (f"No course here is labelled '{category}' (this department leaves the category blank "
                             "for many courses), so the category filter was NOT applied. Treat the listed courses "
                             "as the answer and say that their category is not specified in the course list.")
    if slot:
        rows = [r for r in rows if r["slot"].upper().split(" ")[0] == slot.upper().strip()]
        applied["slot"] = slot.upper()
    # one course can be listed twice in a sheet (e.g. a core for two programmes)
    seen, uniq = set(), []
    for r in rows:
        key = (r["course_code"] or r["course_name"]).upper()
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    return {"count": len(uniq), "filters": applied,
            "courses": [{k: r[k] for k in ("course_code", "course_name", "category", "slot", "instructor") if r[k]}
                        for r in uniq[:40]],
            "note": fallback_note or "category column is blank for some departments",
            "source": COURSE_SRC}


def get_slot_timings(slot: str) -> dict:
    """Days and times at which a timetable slot meets (theory slots A-K, N, U, V; lab slots L1-L10, M1-M10).

    Args:
        slot: slot name, e.g. "E", "K", "M1".
    """
    s = slot.strip().upper().replace("SLOT", "").strip()
    rows = [r for r in _slots() if r["slot"] == s]
    if not rows:
        return {"found": False, "message": f"Slot '{slot}' is not in the 2nd-year-onwards slot grid "
                                           "(first-year and executive slots are not covered).", "source": SLOT_SRC}
    return {"found": True, "slot": s,
            "meetings": [f"{r['day']} {r['start']}-{r['end']} ({r['kind']})" for r in rows],
            "source": SLOT_SRC}


def _contacts_for(course_row: dict) -> list[dict]:
    out = []
    for field in (course_row["instructor"], course_row.get("co_instructors", "")):
        for name in split_instructors(field):
            f = _faculty().get(name.lower())
            out.append({"name": name, "email": f["email"] if f else "not in directory"})
    return out


def get_instructor_contact(course: str) -> dict:
    """Find the instructor(s) of a course and their e-mail ID.

    Args:
        course: course code (e.g. "CSL7650") or course name.
    """
    hits = _find_courses(course)
    if not hits:
        return {"found": False, "query": course, "source": COURSE_SRC,
                "message": f"'{course}' is not in the AY 2026-27 Semester I course list, so its instructor "
                           "cannot be identified. Ask the student to check the course code."}
    res = []
    for c in hits[:4]:
        res.append({"course_code": c["course_code"], "course_name": c["course_name"],
                    "instructors": _contacts_for(c)})
    return {"found": True, "results": res, "source": f"{COURSE_SRC}; {FACULTY_SRC}"}


def save_email_draft(course: str, purpose: str, details: str = "", student_name: str = "",
                     roll_number: str = "") -> dict:
    """Write an e-mail draft to a course instructor for the student to review. The e-mail is NOT sent.

    Args:
        course: course code or name, e.g. "CSL7650".
        purpose: one of "sick leave", "leave", "makeup exam", or a short free-text purpose.
        details: what the student said: number of days, dates, reason, which exam was missed, etc.
        student_name: student's name if given, else leave empty.
        roll_number: student's roll number if given, else leave empty.
    """
    info = get_instructor_contact(course)
    if not info["found"]:
        return {"saved": False, **info}
    c = info["results"][0]
    inst = [i for i in c["instructors"] if "@" in i["email"]]
    if not inst:
        return {"saved": False, "message": f"No instructor e-mail is listed for {c['course_code']}.",
                "source": info["source"]}
    to = ", ".join(i["email"] for i in inst)
    greet = "Dear Prof. " + inst[0]["name"].split()[-1] if len(inst) == 1 else "Dear Professors"
    name, roll = student_name or "[Your Name]", roll_number or "[Roll Number]"
    p = purpose.lower()
    if "makeup" in p or "make-up" in p or "make up" in p:
        subject = f"Request for make-up examination - {c['course_code']} {c['course_name']}"
        ask = ("I am writing to request permission to appear for a make-up examination. "
               f"{details.strip() or '[State which exam you missed and why.]'} "
               "I will submit the supporting medical certificate from the institute Health Centre "
               "along with the make-up application within the deadline.")
    elif "leave" in p or "sick" in p:
        subject = f"Leave application - {c['course_code']} {c['course_name']}"
        reason = "on medical grounds" if "sick" in p or "ill" in details.lower() else ""
        ask = (f"I am writing to request leave {reason} from the classes of this course. "
               f"{details.strip() or '[Number of days, dates and reason.]'} "
               "I will make up for the missed content and complete any pending work.").replace("  ", " ")
    else:
        subject = f"{purpose.strip().capitalize()} - {c['course_code']} {c['course_name']}"
        ask = details.strip() or "[Write your request here.]"
    body = (f"{greet},\n\nI am {name} ({roll}), registered in {c['course_code']} {c['course_name']}. "
            f"{ask}\n\nKindly consider my request.\n\nThank you,\n{name}\n{roll}\n")
    config.EMAIL_DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.EMAIL_DRAFT_DIR / f"{datetime.now():%Y%m%d-%H%M%S}_{c['course_code'] or 'course'}.txt"
    path.write_text(f"To: {to}\nSubject: {subject}\n\n{body}", encoding="utf-8")
    return {"saved": True, "to": to, "subject": subject, "body": body, "draft_file": str(path.relative_to(config.ROOT)),
            "note": "Draft only - review and send it yourself. E-mail IDs are dummy values.",
            "source": info["source"]}


def log_unanswered_question(question: str, reason: str) -> dict:
    """Record a question the helpdesk cannot answer so a human can respond later.
    Call this whenever you tell the student you don't know.

    Args:
        question: the student's question, verbatim.
        reason: "out_of_scope" (not about academics) or "not_in_documents" (academic but no source found).
    """
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"time": datetime.now().isoformat(timespec="seconds"), "question": question, "reason": reason,
           "logged_by": "agent"}
    with config.UNANSWERED_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"logged": True, "reply_to_student": config.REFUSAL_TEXT}


def search_academic_documents(query: str) -> dict:
    """Search the institute's academic documents (regulations, academic calendar, curriculum,
    fee structure, holiday list, registration guidelines, slot rules) and return the most
    relevant passages with their citation.

    Args:
        query: a focused search query, e.g. "attendance requirement major examination".
    """
    from helpdesk.rag.store import search
    hits, best = search(query, k=config.TOP_K)
    passages = []
    for h in hits:
        m = h["meta"]
        cite = f"{m['title']}, {m['locator']}"
        if m.get("status") == "superseded":
            cite += " [SUPERSEDED - older batches only]"
        passages.append({"cite_as": cite, "text": h["text"].split("\n", 1)[-1][:1400]})
    # relevant if the dense score is high enough, or dense and BM25 independently agree on the top chunk
    agree = bool(hits) and {"dense", "bm25"} <= set(hits[0].get("rank_sources", []))
    found = bool(passages) and (best >= config.MIN_SIMILARITY or agree)
    return {
        "found": found,
        "best_similarity": best,
        "passages": passages,
        "instruction": ("Answer ONLY from these passages and cite the 'cite_as' of the passage you used. "
                        "Prefer current documents over SUPERSEDED ones. If the passages do not contain the "
                        "answer, say you don't know and call log_unanswered_question.")
        if found else
        "No passage is relevant enough. Tell the student you don't know and call log_unanswered_question.",
    }
