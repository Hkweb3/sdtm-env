```python
import os
import re
import calendar
from datetime import date

import pandas as pd

INPUT_DIR = "input"
OUTPUT_DIR = "output"
STUDYID = "PLX-658"
DOMAIN = "DM"

MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

ARM_MAP = {
    "A": ("PBO", "Placebo"),
    "B": ("XANLO", "Xanomeline Low Dose"),
    "C": ("XANHI", "Xanomeline High Dose"),
}

RACE_MAP = {
    "1": "1",
    "WHITE": "1",
    "2": "2",
    "BLACK OR AFRICAN AMERICAN": "2",
    "3": "3",
    "ASIAN": "3",
    "4": "4",
    "AMERICAN INDIAN OR ALASKA NATIVE": "4",
    "5": "5",
    "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER": "5",
}


def parse_raw_date(value):
    if value is None:
        return None

    s = str(value).strip().upper()
    if not s:
        return None

    m = re.fullmatch(r"(UN|\d{2})(UNK|[A-Z]{3})(\d{4})", s)
    if not m:
        return None

    day_s, mon_s, year_s = m.groups()

    try:
        year = int(year_s)
    except ValueError:
        return None

    if year < 1 or year > 9999:
        return None

    if day_s == "UN":
        day = None
    else:
        try:
            day = int(day_s)
        except ValueError:
            return None
        if day < 1 or day > 31:
            return None

    if mon_s == "UNK":
        month = None
    else:
        month = MONTHS.get(mon_s)
        if month is None:
            return None

    if month is not None and day is not None:
        if day > calendar.monthrange(year, month)[1]:
            return None
        iso = f"{year:04d}-{month:02d}-{day:02d}"
    elif month is not None:
        iso = f"{year:04d}-{month:02d}"
    else:
        iso = f"{year:04d}"

    return iso, year, month, day


def possible_dates(year, month, day):
    if year is None or year < 1 or year > 9999:
        return

    if month is None and day is None:
        for m in range(1, 13):
            last = calendar.monthrange(year, m)[1]
            for d in range(1, last + 1):
                yield date(year, m, d)
    elif month is not None and day is None:
        if month < 1 or month > 12:
            return
        last = calendar.monthrange(year, month)[1]
        for d in range(1, last + 1):
            yield date(year, month, d)
    elif month is None and day is not None:
        if day < 1 or day > 31:
            return
        for m in range(1, 13):
            if calendar.monthrange(year, m)[1] >= day:
                yield date(year, m, day)
    else:
        try:
            yield date(year, month, day)
        except ValueError:
            return


def compute_age(by, bm, bd, cy, cm, cd):
    if by is None or cy is None:
        return ""

    births = list(possible_dates(by, bm, bd))
    consents = list(possible_dates(cy, cm, cd))

    if not births or not consents:
        return ""

    ages = set()
    for b in births:
        for c in consents:
            if c < b:
                return ""

            age = c.year - b.year
            if (c.month, c.day) < (b.month, b.day):
                age -= 1

            if age < 0:
                return ""

            ages.add(age)
            if len(ages) > 1:
                return ""

    return str(ages.pop()) if ages else ""


def first_month_with_day(year, day):
    for m in range(1, 13):
        if calendar.monthrange(year, m)[1] >= day:
            return m
    return 1


def last_month_with_day(year, day):
    for m in range(12, 0, -1):
        if calendar.monthrange(year, m)[1] >= day:
            return m
    return 12


def