# Adapted from Giorgi Kobaidze's MIT-licensed tools/profile/readme.py
# (https://github.com/georgekobaidze/georgekobaidze). See NOTICE and LICENSE.
"""Updates the dynamic parts of README.md from data/*.json.

- the alt text of the stats and contribution-city images
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


def days(n):
    return f"{n} day" if n == 1 else f"{n} days"


def stats_alt(d):
    since = datetime.date.fromisoformat(d["created_at"][:10])
    langs = sorted((d.get("languages") or {}).items(), key=lambda kv: -kv[1])[:5]
    parts = [
        f'{d.get("stars", 0)} total stars',
        f'{d.get("contributions_year", d.get("commits_year", 0))} contributions in {d.get("year")}, '
        f'{d.get("contributions_all", d.get("commits_all", 0))} all time',
        f'{d.get("prs", 0)} pull requests ({d.get("prs_merged", 0)} merged)',
        f'current streak {days(d.get("streak_current", 0))}, longest {days(d.get("streak_longest", 0))}',
        (
        f'{d.get("followers", 0)} follower' if d.get("followers") == 1
        else f'{d.get("followers", 0)} followers'
    ),
        f'member since {since:%B %Y}',
    ]
    if d.get("forks") is not None:
        parts.append(f'{d.get("forks", 0)} forks')
    if d.get("accounts"):
        parts.append(f'aggregated across {d["accounts"]} accounts')
    text = "Stats: " + "; ".join(parts) + "."
    if langs:
        text += " Top languages: " + ", ".join(k for k, _ in langs) + "."
    return html.escape(text, quote=True)


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

    s, n = re.subn(
        r'(<img src="\./assets/stats\.svg"[^>]*?alt=")[^"]*(")',
        lambda m: m.group(1) + stats_alt(stats) + m.group(2),
        s,
    )
    if n != 1:
        sys.exit("error: README needs exactly one stats.svg image with an alt attribute")

    cal_file = DATA / "calendar.json"
    if cal_file.exists():
        s, n = re.subn(
            r'(<img src="\./assets/contribution-city\.svg"[^>]*?alt=")[^"]*(")',
            lambda m: m.group(1) + city_alt(json.loads(cal_file.read_text())) + m.group(2),
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
