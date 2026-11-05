"""Department sheet names in the course list, their display names and the aliases students use."""
import re

# sheet name -> (department name used in answers, aliases a student might type)
DEPARTMENTS = {
    "EE": ("Electrical Engineering", ["ee", "electrical"]),
    "ECE": ("Electronics and Communication Engineering", ["ece", "electronics", "ec"]),
    "SoLA": ("School of Liberal Arts (Humanities and Social Sciences)",
             ["sola", "humanities", "hss", "liberal arts", "humanities and social sciences", "social sciences"]),
    "CET": ("Centre for Education Technology (ITEP / Education)", ["cet", "education", "itep"]),
    "CIE": ("Civil and Infrastructure Engineering", ["cie", "civil", "civil and infrastructure"]),
    "MT": ("Metallurgical and Materials Engineering", ["mt", "materials", "metallurgy", "mme"]),
    "Aero": ("Aerospace (Drone and Anti-Drone Technologies)", ["aero", "aerospace", "dadt", "drone"]),
    "EnAuto": ("Energy and Automotive Engineering", ["enauto", "energy", "automotive", "energy engineering"]),
    "BSBE": ("Bioscience and Bioengineering", ["bsbe", "bioengineering", "bioscience", "bio"]),
    "Math": ("Mathematics", ["math", "maths", "mathematics"]),
    "Chemical": ("Chemical Engineering", ["chemical", "che", "chemical engineering"]),
    "AIDE": ("AI and Data Engineering", ["aide", "ai", "data science", "ai and data science", "ai and data engineering"]),
    "CSE": ("Computer Science and Engineering", ["cse", "cs", "computer science"]),
    "MedTech": ("Medical Technologies", ["medtech", "medical technology", "medical technologies"]),
    "SME": ("School of Management and Entrepreneurship", ["sme", "management", "mba"]),
    "Physics": ("Physics", ["physics", "ph"]),
    "Chemistry": ("Chemistry", ["chemistry", "cy"]),
    "SOD": ("School of Design", ["sod", "design"]),
    "ME": ("Mechanical Engineering", ["me", "mechanical"]),
    "DESE": ("Environment and Sustainability (DESE)", ["dese", "environment", "sustainability"]),
}


TITLE_RE = re.compile(r"^(prof\.?|dr\.?|mr\.?|ms\.?)\s+", re.I)


def split_instructors(field: str) -> list[str]:
    field = re.sub(r"\(.*?\)", "", field)          # "(Allocated by Dean ...)", "(1.5)"
    field = field.replace("**", "").replace("*", "")
    parts = re.split(r",|;|/|\+| and |&", field)
    names = []
    for p in parts:
        p = TITLE_RE.sub("", p.strip())
        p = re.sub(r"\s+HEP$", "", p)                # "Jitendra Kumar HEP"
        if len(p) >= 3 and p.upper() not in ("TBD", "NA", "-"):
            names.append(p.strip())
    return names
