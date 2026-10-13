import re

# Conventional state registrations and Bharat-series syntax. This is a syntax
# check, not proof of an issued registration. Special/military plates need review.
STATES = "AN AP AR AS BR CG CH DD DL DN GA GJ HP HR JH JK KA KL LA LD MH ML MN MP MZ NL OD OR PB PY RJ SK TN TR TS TG UK UP UT WB".split()
STANDARD = re.compile(r"(?:" + "|".join(STATES) + r")[0-9]{1,2}[A-Z]{1,3}[0-9]{1,4}")
BHARAT = re.compile(r"[0-9]{2}BH[0-9]{4}[A-HJ-NP-Z]{1,2}")


def normalize_plate(raw: str) -> str:
    # Only remove separators; never infer O/0, I/1, B/8 or S/5.
    return re.sub(r"[\s-]+", "", raw.upper())


def valid_plate(plate: str) -> bool:
    return bool(STANDARD.fullmatch(plate) or BHARAT.fullmatch(plate))
