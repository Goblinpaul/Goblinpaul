# Adapted from Giorgi Kobaidze's MIT-licensed tools/profile/readme.py
# (https://github.com/georgekobaidze/georgekobaidze). See NOTICE and LICENSE.
"""Updates the dynamic parts of README.md from data/*.json.

- the alt text of the stats, builds, and contribution-city images
- the project-card block between <!-- projects:start --> and <!-- projects:end -->

Everything else in the README is left exactly as it is. There is no
writing or links section.
"""
from __future__ import annotations

import datetime
import html
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
README = HERE.parent.parent / "README.md"
DATA = HERE / "data"
PROJECTS_FILE = HERE / "projects.json"

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from render import series_metrics  # noqa: E402


def days(n):
    return f"{n} day" if n == 1 else f"{n} days"


def stats_alt(d, calendar=None):
    since = datetime.date.fromisoformat(d["created_at"][:10])
    langs = sorted((d.get("languages") or {}).items(), key=lambda kv: -kv[1])[:5]
    year = d.get("year")
    parts = []
    if d.get("commits_year"):
        bit = f'{d["commits_year"]:,} commits in {year}'
        if d.get("commits_all") and d["commits_all"] != d["commits_year"]:
            bit += f', {d["commits_all"]:,} all time'
        parts.append(bit)
    cy = d.get("contributions_year", d.get("commits_year", 0))
    ca = d.get("contributions_all", d.get("commits_all", 0))
    if cy:
        bit = f'{cy:,} contributions in {year}'
        if ca:
            bit += f', {ca:,} all time'
        parts.append(bit)
    if d.get("prs"):
        bit = f'{d.get("prs", 0):,} pull requests'
        if d.get("prs_merged"):
            bit += f' ({d["prs_merged"]:,} merged)'
        parts.append(bit)
    if d.get("streak_current") or d.get("streak_longest"):
        parts.append(
            f'current streak {days(d.get("streak_current", 0))}, longest {days(d.get("streak_longest", 0))}'
        )
    m = series_metrics(calendar) if calendar else None
    if m and m["active"]:
        parts.append(f'{m["active"]} active days')
    if m and m["busiest"]:
        bd, bn = m["busiest"]
        parts.append(f'busiest day {bd:%B} {bd.day} with {bn:,}')
    if d.get("repos_owned"):
        parts.append(f'{d["repos_owned"]:,} owned repos')
    if d.get("repos_contributed"):
        parts.append(f'{d["repos_contributed"]:,} contributed repos')
    parts.append(f'member since {since:%B %Y}')
    if d.get("accounts"):
        parts.append(f'aggregated across {d["accounts"]} accounts')
    text = "Stats: " + "; ".join(parts) + "."
    if langs:
        text += " Top languages: " + ", ".join(k for k, _ in langs) + "."
    return html.escape(text, quote=True)



def load_snapshot_days():
    path = DATA / "snapshot.json"
    try:
        raw = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    days = {}
    for item in raw.get("days") or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        try:
            key = str(item[0])
            datetime.date.fromisoformat(key)
            n = int(item[1] or 0)
        except (TypeError, ValueError):
            continue
        if n > 0:
            days[key] = n
    return days


def merge_snapshot_calendar(calendar):
    extra = load_snapshot_days()
    if not extra:
        return calendar, 0
    merged = []
    added = 0
    for day, n in calendar:
        add = extra.get(day, 0)
        merged.append([day, int(n or 0) + add])
        added += add
    return merged, added


def city_alt(calendar):
    total = sum(n for _, n in calendar)
    busiest = max(calendar, key=lambda t: t[1]) if calendar else None
    text = (
        "Contribution city: an isometric skyline with one building per day of the last year. "
        f"{total:,} contributions"
    )
    if busiest and busiest[1]:
        d = datetime.date.fromisoformat(busiest[0])
        text += f", busiest day {d:%B} {d.day} with {busiest[1]}"
    return html.escape(text + ".", quote=True)



def builds_alt(calendar):
    m = series_metrics(calendar)
    text = (
        f"Build stats: {m['total']:,} contributions in the last year; "
        f"daily average {m['avg']:.1f}; {m['active']} active days ({m['pct']}% of the year); "
        f"current streak {days(m['streak'])}."
    )
    return html.escape(text, quote=True)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "project"


def projects_block():
    try:
        projects = json.loads(PROJECTS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        projects = []
    if not projects:
        return "<!-- projects:start -->\n<!-- projects:end -->"
    lines = []
    # pair cards two-across, same as the reference README
    row = []
    for p in projects:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        slug = p.get("slug") or slugify(p["name"])
        url = html.escape(p.get("url") or "#", quote=True)
        desc = (p.get("description") or "").strip()
        langs = ", ".join(p.get("languages") or [])
        alt = p["name"] + (f" — {desc}" if desc else "") + (f" {langs}." if langs else ".")
        img = (
            f'<a href="{url}"><img src="./assets/card-{html.escape(slug, quote=True)}.svg" '
            f'width="50%" align="top" alt="{html.escape(alt, quote=True)}"></a>'
        )
        row.append(img)
        if len(row) == 2:
            lines.append("".join(row))
            row = []
    if row:
        lines.append("".join(row))
    return "<!-- projects:start -->\n" + "\n".join(lines) + "\n<!-- projects:end -->"


def main():
    stats = json.loads((DATA / "stats.json").read_text())
    s = README.read_text()

    cal_file = DATA / "calendar.json"
    calendar = json.loads(cal_file.read_text()) if cal_file.exists() else []
    if calendar:
        city_cal, _snapshot_added = merge_snapshot_calendar(calendar)
    else:
        city_cal = []

    s, n = re.subn(
        r'(<img src="\./assets/stats\.svg"[^>]*?alt=")[^"]*(")',
        lambda m: m.group(1) + stats_alt(stats, calendar=city_cal) + m.group(2),
        s,
    )
    if n != 1:
        sys.exit("error: README needs exactly one stats.svg image with an alt attribute")

    if city_cal and "./assets/builds.svg" in s:
        s, n = re.subn(
            r'(<img src="\./assets/builds\.svg"[^>]*?alt=")[^"]*(")',
            lambda m: m.group(1) + builds_alt(city_cal) + m.group(2),
            s,
        )
        if n != 1:
            sys.exit("error: README needs exactly one builds.svg image with an alt attribute")

    if city_cal:
        s, n = re.subn(
            r'(<img src="\./assets/contribution-city\.svg"[^>]*?alt=")[^"]*(")',
            lambda m: m.group(1) + city_alt(city_cal) + m.group(2),
            s,
        )
        if n != 1:
            sys.exit("error: README needs exactly one contribution-city.svg image with an alt attribute")

    s, n = re.subn(
        r"<!-- projects:start -->.*?<!-- projects:end -->",
        lambda _: projects_block(),
        s,
        flags=re.S,
    )
    if n != 1:
        sys.exit("error: README needs exactly one <!-- projects:start --> … <!-- projects:end --> block")

    README.write_text(s)
    print("README updated")


if __name__ == "__main__":
    main()
