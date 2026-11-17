# Adapted from Giorgi Kobaidze's MIT-licensed tools/profile/fetch.py
# (https://github.com/georgekobaidze/georgekobaidze). See NOTICE and LICENSE.
"""Fetches GitHub stats for the configured accounts and writes only
aggregated numbers to data/stats.json and data/calendar.json.

Committed data files, the rendered SVGs, README alt text, the workflow,
and log output must never contain repo names, org names, client names,
or any account username.
tools/profile/accounts.json is a generic schema/example only and is
never read at runtime.

Accounts are loaded, in order, from:
  1. PROFILE_ACCOUNTS — comma-separated username=ENVVAR pairs, e.g.
     "u1=TOKEN_1,u2=TOKEN_2". This is the GitHub
     Actions secret.
  2. tools/profile/accounts.local.json — gitignored local fallback
     with the same {username, token_env} shape as the example file.
Empty usernames are skipped.

Each ENVVAR, if set, should be a classic PAT (repo + read:user) for
that account. That enables GraphQL contributionsCollection with
restricted/private contributions, plus private owned and contributed-to
repos (stars, PRs, languages). GITHUB_TOKEN is the Actions token used
as a public GraphQL fallback when an account has no PAT.

With no token at all, public REST plus the public contributions HTML
calendar are used. Each account is fetched independently; a failure on
one keeps the others. Totals are summed; repos are deduped by id;
streaks are computed on the merged daily calendar; member since is the
earliest created_at. Language shares are an equal-repo average of each
repo's own language mix (not raw bytes), with HTML/CSS and similar
markup down-weighted, so generated pages do not dominate the bar.

In Actions, every username is registered with ::add-mask::
and stripped from printed messages.

data/snapshot.json is a frozen, one-time daily-count snapshot.
This script must never fetch or overwrite that file. render.py merges
those per-day values into the contribution city at render time.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"
ACCOUNTS_EXAMPLE = HERE / "accounts.json"  # schema only, not read
ACCOUNTS_LOCAL = HERE / "accounts.local.json"  # gitignored
UA = "profile-stats-updater"

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # noqa: BLE001
    TZ = datetime.timezone(datetime.timedelta(hours=-3))

STATS_KEYS = (
    "created_at",
    "followers",
    "prs",
    "prs_merged",
    "stars",
    "forks",
    "languages",
    "year",
    "commits_year",
    "commits_all",
    "contributions_year",
    "contributions_all",
    "streak_current",
    "streak_longest",
    "accounts",
    "repos_owned",
    "repos_contributed",
    "updated",
)


# ─────────────────────────────── helpers ───────────────────────────────
def _open(req, timeout=30, attempts=3):
    last = None
    for i in range(attempts):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except Exception as ex:  # noqa: BLE001
            last = ex
            if i + 1 < attempts:
                import time
                time.sleep(0.8 * (i + 1))
    raise last


def http_json(url, *, headers=None, body=None, timeout=30):
    req = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode(),
        headers={"User-Agent": UA, "Accept": "application/vnd.github+json", **(headers or {})},
    )
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with _open(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def http_text(url, *, headers=None, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with _open(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def graphql(token, query, variables=None):
    res = http_json(
        "https://api.github.com/graphql",
        headers={"Authorization": f"bearer {token}", "Accept": "application/json"},
        body={"query": query, "variables": variables or {}},
    )
    if res.get("errors"):
        raise RuntimeError("GraphQL error: " + "; ".join(e.get("message", "?") for e in res["errors"]))
    return res["data"]


def load(name, default):
    try:
        return json.loads((DATA / name).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(name, obj):
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


_MASKED: list[str] = []  # usernames that must never appear in logs


def mask_login(login: str) -> None:
    """Register a username so it never appears in logs."""
    login = (login or "").strip().lstrip("@")
    if not login:
        return
    key = login.lower()
    existing = {m.lower() for m in _MASKED}
    if key in existing:
        return
    _MASKED.append(login)
    quoted = urllib.parse.quote(login)
    if quoted != login and quoted.lower() not in existing:
        _MASKED.append(quoted)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::add-mask::{login}")
        if quoted != login:
            print(f"::add-mask::{quoted}")


def register_masks(accounts: list[dict]) -> None:
    """Register every account username with log masking."""
    for row in accounts:
        mask_login(row.get("username") or "")


def redact(msg) -> str:
    s = str(msg)
    for login in sorted(_MASKED, key=len, reverse=True):
        s = re.sub(re.escape(login), "***", s, flags=re.I)
    return s


def warn(msg):
    msg = redact(msg)
    print(f"::warning::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"warning: {msg}", file=sys.stderr)


def today_local() -> datetime.date:
    return datetime.datetime.now(TZ).date()


def _rows_from_pairs(pairs: list[tuple[str, str]]) -> list[dict]:
    accounts = []
    for i, (login, env) in enumerate(pairs, start=1):
        login = login.strip()
        env = env.strip()
        if not login:
            continue
        accounts.append({"username": login, "token_env": env, "index": i})
    return accounts


def _parse_profile_accounts(raw: str) -> list[dict]:
    pairs = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise SystemExit("PROFILE_ACCOUNTS entries must be username=ENVVAR pairs")
        login, env = chunk.split("=", 1)
        pairs.append((login, env))
    return _rows_from_pairs(pairs)


def _parse_accounts_file(path: pathlib.Path) -> list[dict]:
    raw = json.loads(path.read_text())
    pairs = []
    if not isinstance(raw, list):
        raise SystemExit(f"{path.name} must be a JSON array of {{username, token_env}} objects")
    for row in raw:
        if not isinstance(row, dict):
            continue
        pairs.append(((row.get("username") or ""), (row.get("token_env") or "")))
    return _rows_from_pairs(pairs)


def load_accounts() -> list[dict]:
    env = (os.environ.get("PROFILE_ACCOUNTS") or "").strip()
    if env:
        accounts = _parse_profile_accounts(env)
        source = "PROFILE_ACCOUNTS"
    elif ACCOUNTS_LOCAL.exists():
        accounts = _parse_accounts_file(ACCOUNTS_LOCAL)
        source = ACCOUNTS_LOCAL.name
    else:
        raise SystemExit(
            "no accounts configured: set PROFILE_ACCOUNTS or create "
            "gitignored tools/profile/accounts.local.json "
            "(see tools/profile/accounts.json for the schema)"
        )
    if not accounts:
        raise SystemExit(f"{source} listed no usernames to fetch")
    register_masks(accounts)
    return accounts


def token_for(row: dict) -> str | None:
    env = row.get("token_env") or ""
    tok = os.environ.get(env) if env else None
    return tok or None


# ─────────────────────────────── streaks / calendar ────────────────────────────────
def streaks(days, today):
    """days: {date: count}. Current streak may end yesterday if today is still empty."""
    dates = sorted(d for d in days if d <= today)
    longest = run = 0
    for d in dates:
        run = run + 1 if days[d] > 0 else 0
        longest = max(longest, run)
    current, d = 0, today
    if days.get(d, 0) == 0:
        d -= datetime.timedelta(days=1)
    while days.get(d, 0) > 0:
        current += 1
        d -= datetime.timedelta(days=1)
    return current, longest


def last_53_weeks(days, today):
    start = today - datetime.timedelta(weeks=52)
    start -= datetime.timedelta(days=(start.weekday() + 1) % 7)  # Sunday, like GitHub's graph
    return [
        [d.isoformat(), days.get(d, 0)]
        for d in (start + datetime.timedelta(days=i) for i in range((today - start).days + 1))
    ]


def add_days(dst: dict, src: dict) -> None:
    for d, n in src.items():
        dst[d] = dst.get(d, 0) + int(n or 0)


# ─────────────────────────────── GraphQL ────────────────────────────────
PROFILE_QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    pullRequests { totalCount }
    merged: pullRequests(states: MERGED) { totalCount }
    contributionsCollection { contributionYears }
  }
}
"""

REPOS_PAGE = """
query($login: String!, $ownAfter: String, $contribAfter: String, $wantOwn: Boolean!, $wantContrib: Boolean!) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100, after: $ownAfter) @include(if: $wantOwn) {
      pageInfo { hasNextPage endCursor }
      nodes {
        databaseId
        stargazerCount
        forkCount
        languages(first: 20) { edges { size node { name } } }
      }
    }
    repositoriesContributedTo(
      first: 100
      after: $contribAfter
      includeUserRepositories: false
      contributionTypes: [COMMIT, PULL_REQUEST, PULL_REQUEST_REVIEW]
    ) @include(if: $wantContrib) {
      pageInfo { hasNextPage endCursor }
      nodes {
        databaseId
        languages(first: 20) { edges { size node { name } } }
      }
    }
  }
}
"""


def years_query(years):
    parts = []
    for y in years:
        parts.append(f"""
    y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z") {{
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar {{ totalContributions weeks {{ contributionDays {{ date contributionCount }} }} }}
    }}""")
    return "query($login: String!) {\n  user(login: $login) {" + "".join(parts) + "\n  }\n}"


# Markup is counted by file bytes and is often generated by frameworks.
# It still gets a vote so real frontend work is visible, but at 1/5 weight.
MARKUP_LANGS = frozenset({"HTML", "CSS", "SCSS", "Sass", "Less"})
MARKUP_WEIGHT = 0.2


def _lang_map(node) -> dict[str, int]:
    out = {}
    for edge in (node or {}).get("languages", {}).get("edges") or []:
        name = (edge.get("node") or {}).get("name")
        size = edge.get("size") or 0
        if name and size:
            out[name] = out.get(name, 0) + int(size)
    return out


def repo_language_share(langs: dict) -> dict[str, float]:
    """Per-repo mix: markup bytes down-weighted, then normalized to 1."""
    weighted: dict[str, float] = {}
    for name, size in (langs or {}).items():
        try:
            n = float(size or 0)
        except (TypeError, ValueError):
            continue
        if n <= 0 or not name:
            continue
        w = MARKUP_WEIGHT if name in MARKUP_LANGS else 1.0
        weighted[name] = weighted.get(name, 0.0) + n * w
    total = sum(weighted.values())
    if total <= 0:
        return {}
    return {name: size / total for name, size in weighted.items()}


def average_language_shares(repo_langs) -> dict[str, float]:
    """Equal vote per repo that has a language breakdown. No repo names."""
    sums: dict[str, float] = {}
    n = 0
    for langs in repo_langs:
        share = repo_language_share(langs)
        if not share:
            continue
        n += 1
        for name, part in share.items():
            sums[name] = sums.get(name, 0.0) + part
    if not n:
        return {}
    averaged = {name: round(part / n, 6) for name, part in sums.items()}
    return dict(sorted(averaged.items(), key=lambda kv: -kv[1]))


def fetch_repos_graphql(token, login):
    """Return (owned, contrib) maps keyed by databaseId. No names."""
    owned, contrib = {}, {}
    own_after = contrib_after = None
    want_own = want_contrib = True
    while want_own or want_contrib:
        u = graphql(
            token,
            REPOS_PAGE,
            {
                "login": login,
                "ownAfter": own_after,
                "contribAfter": contrib_after,
                "wantOwn": want_own,
                "wantContrib": want_contrib,
            },
        )["user"]
        if want_own:
            conn = u.get("repositories") or {}
            for n in conn.get("nodes") or []:
                rid = n.get("databaseId")
                if rid is None:
                    continue
                owned[rid] = {
                    "stars": int(n.get("stargazerCount") or 0),
                    "forks": int(n.get("forkCount") or 0),
                    "langs": _lang_map(n),
                }
            info = conn.get("pageInfo") or {}
            if info.get("hasNextPage"):
                own_after = info.get("endCursor")
            else:
                want_own = False
        if want_contrib:
            conn = u.get("repositoriesContributedTo") or {}
            for n in conn.get("nodes") or []:
                rid = n.get("databaseId")
                if rid is None:
                    continue
                contrib[rid] = {"langs": _lang_map(n)}
            info = conn.get("pageInfo") or {}
            if info.get("hasNextPage"):
                contrib_after = info.get("endCursor")
            else:
                want_contrib = False
    return owned, contrib


def fetch_account_graphql(token, login, today):
    u = graphql(token, PROFILE_QUERY, {"login": login})["user"]
    years = sorted(u["contributionsCollection"]["contributionYears"] or [])
    ydata = graphql(token, years_query(years), {"login": login})["user"] if years else {}

    days, commits_all, contribs_all = {}, 0, 0
    for y in years:
        c = ydata[f"y{y}"]
        commits_all += c["totalCommitContributions"]
        contribs_all += c["contributionCalendar"]["totalContributions"]
        for w in c["contributionCalendar"]["weeks"]:
            for day in w["contributionDays"]:
                d = datetime.date.fromisoformat(day["date"])
                days[d] = days.get(d, 0) + int(day["contributionCount"] or 0)
    cur = ydata.get(f"y{today.year}", {})
    owned, contrib = fetch_repos_graphql(token, login)
    return {
        "created_at": u["createdAt"],
        "followers": u["followers"]["totalCount"],
        "prs": u["pullRequests"]["totalCount"],
        "prs_merged": u["merged"]["totalCount"],
        "commits_year": cur.get("totalCommitContributions", 0),
        "commits_all": commits_all,
        "contributions_year": cur.get("contributionCalendar", {}).get("totalContributions", 0),
        "contributions_all": contribs_all,
        "_days": days,
        "_owned": owned,
        "_contrib": contrib,
    }


# ─────────────────────────────── public fallback ────────────────────────────────
TIP_RE = re.compile(
    r'<tool-tip[^>]*\bfor="([^"]+)"[^>]*>\s*(No|\d[\d,]*) contributions? on [^<]+</tool-tip>',
    re.I,
)
CELL_RE = re.compile(
    r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*\bid="([^"]+)"[^>]*data-level="(\d+)"'
    r'|\bid="([^"]+)"[^>]*data-date="(\d{4}-\d{2}-\d{2})"[^>]*data-level="(\d+)"'
)


def parse_contributions_html(html: str) -> dict[datetime.date, int]:
    id_to_date: dict[str, datetime.date] = {}
    for m in CELL_RE.finditer(html):
        if m.group(1):
            date_s, cid = m.group(1), m.group(2)
        else:
            cid, date_s = m.group(4), m.group(5)
        id_to_date[cid] = datetime.date.fromisoformat(date_s)
    days: dict[datetime.date, int] = {d: 0 for d in id_to_date.values()}
    for cid, raw in TIP_RE.findall(html):
        n = 0 if raw.lower() == "no" else int(raw.replace(",", ""))
        if cid in id_to_date:
            days[id_to_date[cid]] = n
    if not days:
        raise RuntimeError("could not parse contributions calendar HTML")
    return days


def fetch_calendar_year(login: str, year: int) -> dict[datetime.date, int]:
    url = (
        f"https://github.com/users/{urllib.parse.quote(login)}/contributions"
        f"?from={year}-01-01&to={year}-12-31"
    )
    return parse_contributions_html(http_text(url))


def fetch_account_public(login, today, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else None
    user = http_json(f"https://api.github.com/users/{urllib.parse.quote(login)}", headers=headers)
    created = datetime.date.fromisoformat(user["created_at"][:10])
    repos, page = [], 1
    while True:
        batch = http_json(
            f"https://api.github.com/users/{urllib.parse.quote(login)}/repos"
            f"?per_page=100&page={page}&type=owner&sort=updated",
            headers=headers,
        )
        if not isinstance(batch, list) or not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    owned = {}
    for r in repos:
        if r.get("fork"):
            continue
        rid = r.get("id")
        if rid is None:
            continue
        langs = {}
        try:
            breakdown = http_json(r["languages_url"], headers=headers)
            if isinstance(breakdown, dict):
                for name, size in breakdown.items():
                    if isinstance(size, int) and name:
                        langs[name] = size
        except Exception as ex:  # noqa: BLE001
            warn(f"language breakdown unavailable: {redact(ex)}")
        owned[rid] = {
            "stars": int(r.get("stargazers_count") or 0),
            "forks": int(r.get("forks_count") or 0),
            "langs": langs,
        }

    prs = prs_merged = 0
    try:
        q_headers = dict(headers or {})
        # Search needs a token for reliable results; still try without.
        prs = http_json(
            "https://api.github.com/search/issues?"
            + urllib.parse.urlencode({"q": f"type:pr author:{login}"}),
            headers=headers,
        ).get("total_count", 0)
        prs_merged = http_json(
            "https://api.github.com/search/issues?"
            + urllib.parse.urlencode({"q": f"type:pr author:{login} is:merged"}),
            headers=headers,
        ).get("total_count", 0)
        del q_headers
    except Exception as ex:  # noqa: BLE001
        warn(f"PR search unavailable: {redact(ex)}")

    days: dict[datetime.date, int] = {}
    for y in range(created.year, today.year + 1):
        try:
            add_days(days, fetch_calendar_year(login, y))
        except Exception as ex:  # noqa: BLE001
            warn(f"contributions calendar for {y} unavailable: {redact(ex)}")
    if not days:
        raise RuntimeError("no contribution calendar could be fetched")

    contribs_year = sum(n for d, n in days.items() if d.year == today.year)
    contribs_all = sum(days.values())
    return {
        "created_at": user["created_at"],
        "followers": user.get("followers", 0),
        "prs": prs,
        "prs_merged": prs_merged,
        "commits_year": contribs_year,  # public fallback cannot split commits from contributions
        "commits_all": contribs_all,
        "contributions_year": contribs_year,
        "contributions_all": contribs_all,
        "_days": days,
        "_owned": owned,
        "_contrib": {},
    }


def fetch_one(row: dict, today: datetime.date, public_token: str | None) -> tuple[dict, str]:
    login = row["username"]
    pat = token_for(row)
    if pat:
        try:
            return fetch_account_graphql(pat, login, today), "graphql (restricted included)"
        except Exception as ex:  # noqa: BLE001
            warn(f"account {row['index']}: GraphQL with account token failed ({redact(ex)}); trying fallback")
    if public_token:
        try:
            return fetch_account_graphql(public_token, login, today), "graphql (public only)"
        except Exception as ex:  # noqa: BLE001
            warn(f"account {row['index']}: public GraphQL failed ({redact(ex)}); trying REST fallback")
    return fetch_account_public(login, today, token=public_token), "public REST/HTML"


def aggregate(parts: list[dict], today: datetime.date, n_accounts: int) -> tuple[dict, list]:
    days: dict[datetime.date, int] = {}
    owned: dict = {}
    lang_repos: dict = {}
    followers = prs = prs_merged = 0
    commits_year = commits_all = contrib_year = contrib_all = 0
    created_at = None

    for p in parts:
        followers += int(p.get("followers") or 0)
        prs += int(p.get("prs") or 0)
        prs_merged += int(p.get("prs_merged") or 0)
        commits_year += int(p.get("commits_year") or 0)
        commits_all += int(p.get("commits_all") or 0)
        contrib_year += int(p.get("contributions_year") or 0)
        contrib_all += int(p.get("contributions_all") or 0)
        add_days(days, p.get("_days") or {})
        ca = p.get("created_at")
        if ca and (created_at is None or ca < created_at):
            created_at = ca
        for rid, rec in (p.get("_owned") or {}).items():
            if rid not in owned:
                owned[rid] = rec
            else:
                # Same repo, already counted once. Keep the larger public totals.
                owned[rid]["stars"] = max(owned[rid]["stars"], rec.get("stars") or 0)
                owned[rid]["forks"] = max(owned[rid]["forks"], rec.get("forks") or 0)
        for rid, rec in (p.get("_contrib") or {}).items():
            if rid in owned or rid in lang_repos:
                continue
            lang_repos[rid] = dict(rec.get("langs") or {})

    langs = average_language_shares(
        [rec.get("langs") or {} for rec in owned.values()]
        + list(lang_repos.values())
    )

    current, longest = streaks(days, today)
    stats = {
        "created_at": created_at,
        "followers": followers,
        "prs": prs,
        "prs_merged": prs_merged,
        "stars": sum(r.get("stars") or 0 for r in owned.values()),
        "forks": sum(r.get("forks") or 0 for r in owned.values()),
        "languages": dict(sorted(langs.items(), key=lambda kv: -kv[1])),
        "year": today.year,
        "commits_year": commits_year,
        "commits_all": commits_all,
        "contributions_year": contrib_year,
        "contributions_all": contrib_all,
        "streak_current": current,
        "streak_longest": longest,
        "accounts": n_accounts,
        "repos_owned": len(owned),
        "repos_contributed": len(lang_repos),
    }
    return stats, last_53_weeks(days, today)



def public_stats(stats: dict) -> dict:
    return {k: stats[k] for k in STATS_KEYS if k in stats}


# ──────────────────────────────── main ─────────────────────────────────
def main():
    today = today_local()
    accounts = load_accounts()
    public_token = os.environ.get("GITHUB_TOKEN") or None
    parts = []
    for row in accounts:
        try:
            data, kind = fetch_one(row, today, public_token)
            parts.append(data)
            print(redact(f"account {row['index']}/{len(accounts)}: ok ({kind})"))
        except Exception as ex:  # noqa: BLE001
            warn(f"account {row['index']}: fetch failed, skipping ({redact(ex)})")

    if not parts:
        print("error: every account failed, nothing updated", file=sys.stderr)
        sys.exit(1)

    stats, calendar = aggregate(parts, today, n_accounts=len(accounts))
    stats["updated"] = today.isoformat()
    save("calendar.json", calendar)
    save("stats.json", public_stats(stats))
    print(
        f"  aggregated {stats['accounts']} account(s): "
        f"{stats.get('contributions_year', 0)} contribs in {stats.get('year')}, "
        f"{stats.get('contributions_all', 0)} all time, "
        f"{stats.get('stars', 0)} stars, {stats.get('followers', 0)} followers"
    )



if __name__ == "__main__":
    main()
