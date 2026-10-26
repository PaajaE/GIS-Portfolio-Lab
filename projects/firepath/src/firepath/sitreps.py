"""Situation-report text for the masking rule (validation/MASKING_RULE.md) for fires after 2020, which
ICS-209-PLUS does not cover: InciWeb publications, news and announcements of the incident.

  uv run python -m firepath.sitreps <inciweb-slug> <fire>
  uv run python -m firepath.sitreps --wayback <old-inciweb-incident-id> <fire>     (e.g. 7512 telegraph)

--wayback reads archived copies of the old inciweb.nwcg.gov/incident/<id>/ articles from the Internet
Archive (the 2021 Telegraph pages are gone from InciWeb; web.archive.org is not reachable from the cloud
session, so this runs on the build Mac). Unverified until it runs there.

Saves plain text per item under data/raw/<fire>/sitreps/, the sha256 of each in
provenance/sitreps_<fire>.json, and prints the rule's candidate passages (firing/spotting terms).
The masking decision itself is made by reading the candidates and is recorded in
validation/masked_intervals.json with quotes.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import urllib.error
from datetime import datetime, timezone

from .harvest import PROJECT, RAW, _get

BASE = "https://inciweb.wildfire.gov"
HDR = {"User-Agent": "FirePath/0.1"}      # InciWeb's firewall refuses the harvest UA's comment (403)
TERMS = re.compile(r"(firing|burn ?out|burning operation|backfir|back fire|aerial ignition|\bPSD\b|plastic sphere|"
                   r"spot fire|spotting|long[- ]range)", re.I)


def _text(h: str) -> str:
    m = re.search(r"<main.*?</main>", h, re.S)
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", m.group(0) if m else h, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t))).strip()


def fetch(slug: str, fire: str) -> dict:
    links: set[str] = set()
    for sect in ("incident-information", "incident-publication", "incident-news", "incident-announcement"):
        for p in range(15):
            try:
                h = _get(f"{BASE}/{sect}/{slug}?page={p}", HDR, attempts=1, timeout=60).decode("utf-8", "replace")
            except urllib.error.HTTPError:          # a section the incident does not have, or past its last page
                break
            found = set(re.findall(rf'href="(/incident-(?:publication|news|announcement)/{slug}/[^"?#]+)"', h))
            if p > 0 and not found - links:
                break
            links |= found
    out = RAW / fire / "sitreps"
    out.mkdir(parents=True, exist_ok=True)
    items = {}
    for link in sorted(links):
        name = link.rstrip("/").split("/")[-1][:120]
        t = _text(_get(BASE + link, HDR, timeout=60).decode("utf-8", "replace"))
        (out / f"{name}.txt").write_text(t)
        items[name] = {"url": BASE + link, "chars": len(t), "sha256": hashlib.sha256(t.encode()).hexdigest()}
    man = {"fire": fire, "inciweb_slug": slug, "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "items": items}
    (PROJECT / "provenance" / f"sitreps_{fire}.json").write_text(json.dumps(man, indent=1))
    return man


def fetch_wayback(incident_id: str, fire: str) -> dict:
    cdx = ("https://web.archive.org/cdx/search/cdx?url=inciweb.nwcg.gov/incident/article/"
           f"{incident_id}/*&fl=timestamp,original&filter=statuscode:200&collapse=urlkey&output=json")
    rows = json.loads(_get(cdx, HDR, timeout=120))[1:]
    out = RAW / fire / "sitreps"
    out.mkdir(parents=True, exist_ok=True)
    items = {}
    for ts, orig in rows:
        art = orig.rstrip("/").split("/")[-1]
        snap = f"https://web.archive.org/web/{ts}id_/{orig}"
        h = _get(snap, HDR, timeout=120).decode("utf-8", "replace")
        m = re.search(r"<title>(.*?)</title>", h, re.S)
        t = _text(h)
        name = f"article_{art}"
        (out / f"{name}.txt").write_text(t)
        items[name] = {"url": orig, "snapshot": snap, "title": html.unescape(m.group(1).strip()) if m else None,
                       "chars": len(t), "sha256": hashlib.sha256(t.encode()).hexdigest()}
    man = {"fire": fire, "source": f"Internet Archive copies of inciweb.nwcg.gov/incident/article/{incident_id}/*",
           "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "items": items}
    (PROJECT / "provenance" / f"sitreps_{fire}.json").write_text(json.dumps(man, indent=1))
    return man


def candidates(fire: str, width: int = 250):
    for f in sorted((RAW / fire / "sitreps").glob("*.txt")):
        t, last = f.read_text(), -10**9
        for m in TERMS.finditer(t):
            if m.start() - last >= 300:
                last = m.start()
                yield f.stem, t[max(0, m.start() - width):m.start() + width]


if __name__ == "__main__":
    if sys.argv[1] == "--wayback":
        fire = sys.argv[3]
        print(fire, len(fetch_wayback(sys.argv[2], fire)["items"]), "items")
    else:
        slug, fire = sys.argv[1], sys.argv[2]
        print(fire, len(fetch(slug, fire)["items"]), "items")
    for name, passage in candidates(fire):
        print(f"## {name}\n   ...{passage}...")
