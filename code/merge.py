#!/usr/bin/env python3
"""Curator merge for the Marathon Men knowledge base.

Deterministic and idempotent: reads kb/inbox/*.jsonl (sorted), kb/aliases.json, kb/relation_kinds.json and
the existing kb/queue.json (only to preserve item status fields), and rewrites the canonical files:
  kb/entities.json, relations.json, events.json, claims.json, sources.json, queue.json, report.txt

Ops: entity, relation, event, claim, source (merge/union), update_claim, update_entity, update_source
(`set` replaces scalar fields and replaces list fields wholesale; `add_*` unions), lead, conflict,
resolve {queue_id, resolution, status}. Update/resolve ops that name an unknown id are listed in
report.txt under "orphan updates". Conflicting statuses from two inboxes keep the higher-evidence status
and add a "status-conflict" queue item. A claim with set {"retracted": true, "retract_reason": ...} stays
in claims.json, flagged, and is counted separately in the report.

Set MARATHON_KB=<dir> to run against another kb directory (testing).

Run:  python3 merge.py            (from anywhere)
      python3 merge.py --quiet    (print only the report summary line)
"""
import difflib
import glob
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
KB = os.environ.get("MARATHON_KB") or os.path.join(ROOT, "kb")
INBOX = os.path.join(KB, "inbox")

STATUSES = ["ESTABLISHED", "REPORTED", "DISPUTED", "PODCAST-ONLY", "SPECULATION", "CONTRADICTED"]
# evidence rank used when two inboxes set different statuses on one claim
STATUS_RANK = {"ESTABLISHED": 4, "DISPUTED": 3, "CONTRADICTED": 3, "REPORTED": 2, "PODCAST-ONLY": 1, "SPECULATION": 1}
JOKE_ORDER = {"": 0, "none": 0, "low": 1, "high": 2}
PLACEHOLDER_SUMMARIES = {"", "?", "unknown", "tbd", "todo", "n/a", "none"}

problems = defaultdict(list)  # section -> list of lines for the report


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as e:
        problems["bad canonical file"].append(f"{os.path.relpath(path, ROOT)}: {e}")
        return default


def write_json(name, data):
    path = os.path.join(KB, name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=False)
        fh.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------- aliases
ALIASES = load_json(os.path.join(KB, "aliases.json"), {})
if not isinstance(ALIASES, dict):
    problems["bad canonical file"].append("aliases.json is not an object; ignored")
    ALIASES = {}


def resolve(i):
    """Follow alias chains to the canonical id (cycle-safe)."""
    if not isinstance(i, str):
        return i
    seen = []
    cur = i
    while cur in ALIASES and ALIASES[cur] != cur:
        if cur in seen:
            problems["alias cycles"].append(" -> ".join(seen + [cur]))
            return i
        seen.append(cur)
        cur = ALIASES[cur]
    return cur


def rlist(xs):
    out = []
    for x in xs or []:
        r = resolve(x)
        if r and r not in out:
            out.append(r)
    return out


# ---------------------------------------------------------------- relation kinds
RELATION_KINDS = load_json(os.path.join(KB, "relation_kinds.json"), {})
if not isinstance(RELATION_KINDS, dict) or not RELATION_KINDS:
    problems["bad canonical file"].append("relation_kinds.json missing or not an object; kinds not normalized")
    RELATION_KINDS = {}
# one-off kinds seen in inboxes -> canonical kind (the original is kept in relation["kind_original"])
KIND_MAP = {
    "near": "located_near", "lived_near": "located_near", "adjacent_to": "located_near",
    "identified_in": "appears_in", "shown_in": "appears_in",
    "character_witness_for": "testified_for", "witness_for": "testified_for",
    "commented_on": "wrote_about", "reported_on": "wrote_about", "wrote": "wrote_about",
    "partner_of": "married_to", "spouse_of": "married_to", "girlfriend_of": "married_to",
    "talked_to": "met", "spoke_with": "met", "contacted": "met",
    "lived_in": "lived_at", "resided_at": "lived_at", "roommates_with": "roommate_of",
    "friends_with": "friend_of", "worked_for": "employed_by", "informant": "informant_for",
}
unmapped_kinds = Counter()


def canon_kind(k):
    """-> (canonical kind, original kind or '')."""
    raw = (k or "").strip()
    norm = re.sub(r"[\s\-]+", "_", raw.lower())
    if norm in RELATION_KINDS:
        return norm, (raw if raw != norm else "")
    if norm in KIND_MAP:
        return KIND_MAP[norm], raw
    if RELATION_KINDS:
        unmapped_kinds[norm] += 1
    return norm, (raw if raw != norm else "")


# ---------------------------------------------------------------- helpers
def union(a, b, key=None):
    """Order-preserving union; key() decides identity (default: the value / its JSON)."""
    key = key or (lambda v: json.dumps(v, sort_keys=True) if not isinstance(v, str) else v)
    seen = {key(v) for v in a}
    out = list(a)
    for v in b or []:
        k = key(v)
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


def ref_key(r):
    return (r.get("ep"), r.get("t_seconds"), (r.get("speaker") or "").strip().lower(),
            norm_text(r.get("quote") or "")[:60])


def ev_key(e):
    return (e.get("source_id"), norm_text(e.get("note") or ""))


def ci_union(a, b):
    return union(a, b, key=lambda s: norm_name(s) if isinstance(s, str) else json.dumps(s))


def norm_name(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[’'`\"]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"^(the|a|an) ", "", s)
    return s


def norm_text(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())).strip()


def refine_date(cur, new):
    """True if `new` is a more precise form of `cur` (e.g. 2013-04 -> 2013-04-19)."""
    return bool(cur) and bool(new) and new != cur and new.startswith(cur) and "/" not in cur


def good_summary(s):
    return isinstance(s, str) and s.strip().lower() not in PLACEHOLDER_SUMMARIES


def better_summary(cur, new):
    if not good_summary(new):
        return cur
    if not good_summary(cur) or len(new.strip()) > len(cur.strip()):
        return new.strip()
    return cur


# ---------------------------------------------------------------- read inbox
records = []  # (file, lineno, obj)
for path in sorted(glob.glob(os.path.join(INBOX, "*.jsonl"))):
    fname = os.path.basename(path)
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                problems["bad inbox lines (skipped)"].append(f"{fname}:{n}: {e}")
                continue
            if not isinstance(obj, dict) or "op" not in obj:
                problems["bad inbox lines (skipped)"].append(f"{fname}:{n}: no 'op'")
                continue
            records.append((fname, n, obj))

BASE_OPS = ("entity", "relation", "event", "claim", "source")
op_counts = Counter(o["op"] for _, _, o in records)
for op in op_counts:
    if op not in BASE_OPS + ("update_claim", "update_entity", "update_source", "lead", "conflict", "resolve"):
        problems["unknown ops (skipped)"].append(f"{op}: {op_counts[op]} lines")


def where(f, n):
    return f"{f}:{n}"


# ---------------------------------------------------------------- merge base records
entities, events, claims, sources, relations = {}, {}, {}, {}, {}
origin = defaultdict(list)  # canonical id -> list of original ids that fed it
field_conflicts = []


def note_conflict(cid, field, keep, other, src):
    if keep != other:
        field_conflicts.append(f"{cid}.{field}: kept {keep!r}, also saw {other!r} ({src})")


GEO_FIELDS = ("geo_precision", "geo_source", "geo_note")


def merge_entity(o, f, n):
    oid = o.get("id")
    if not oid:
        problems["records without id (skipped)"].append(where(f, n))
        return
    cid = resolve(oid)
    origin[cid].append(oid)
    e = entities.get(cid)
    name = (o.get("name") or "").strip()
    if e is None:
        e = entities[cid] = {
            "id": cid, "type": o.get("type") or "", "name": name, "aliases": [], "summary": "",
            "dates": {"born": "", "died": "", "active": ""}, "location_ids": [], "tags": [],
            "episodes": [], "lat": None, "lon": None, "source_ids": [], "podcast_refs": [],
            "_named_by_canonical": oid == cid,
        }
    else:
        # the record whose own id is the canonical id names the merged entity
        if oid == cid and not e["_named_by_canonical"] and name:
            if e["name"] and norm_name(e["name"]) != norm_name(name):
                e["aliases"] = ci_union(e["aliases"], [e["name"]])
            e["name"], e["_named_by_canonical"] = name, True
            if o.get("type"):
                e["type"] = o["type"]
        elif name and norm_name(name) != norm_name(e["name"]):
            e["aliases"] = ci_union(e["aliases"], [name])
        if o.get("type") and e["type"] and o["type"] != e["type"]:
            note_conflict(cid, "type", e["type"], o["type"], where(f, n))
        if not e["type"]:
            e["type"] = o.get("type") or ""
    e["aliases"] = ci_union(e["aliases"], [a for a in (o.get("aliases") or []) if isinstance(a, str) and a.strip()])
    e["summary"] = better_summary(e["summary"], o.get("summary"))
    for k, v in (o.get("dates") or {}).items():
        v = (v or "").strip() if isinstance(v, str) else v
        if v:
            if not e["dates"].get(k) or refine_date(e["dates"][k], v):
                e["dates"][k] = v
            elif not refine_date(v, e["dates"][k]):
                note_conflict(cid, f"dates.{k}", e["dates"][k], v, where(f, n))
    e["location_ids"] = union(e["location_ids"], rlist(o.get("location_ids")))
    e["tags"] = union(e["tags"], o.get("tags") or [])
    e["episodes"] = union(e["episodes"], o.get("episodes") or [])
    e["source_ids"] = union(e["source_ids"], rlist(o.get("source_ids")))
    e["podcast_refs"] = union(e["podcast_refs"], o.get("podcast_refs") or [], key=ref_key)
    if e["lat"] is None and o.get("lat") is not None and o.get("lon") is not None:
        e["lat"], e["lon"] = o["lat"], o["lon"]
    elif e["lat"] is not None and o.get("lat") is not None:
        if abs(e["lat"] - o["lat"]) > 0.05 or abs(e["lon"] - o["lon"]) > 0.05:
            note_conflict(cid, "lat/lon", (e["lat"], e["lon"]), (o["lat"], o["lon"]), where(f, n))
    for gk in GEO_FIELDS:  # geo_precision / geo_source / geo_note: first non-empty value wins
        if o.get(gk) and not e.get(gk):
            e[gk] = o[gk]


def merge_event(o, f, n):
    oid = o.get("id")
    if not oid:
        problems["records without id (skipped)"].append(where(f, n))
        return
    cid = resolve(oid)
    origin[cid].append(oid)
    v = events.get(cid)
    title = (o.get("title") or "").strip()
    if v is None:
        v = events[cid] = {
            "id": cid, "title": title, "aliases": [], "date": "", "precision": "", "place_id": "",
            "participants": [], "claim_ids": [], "source_ids": [], "tags": [], "date_note": "",
            "_named_by_canonical": oid == cid, "_prio": -1,
        }
    else:
        if oid == cid and not v["_named_by_canonical"] and title:
            if v["title"] and norm_name(v["title"]) != norm_name(title):
                v["aliases"] = ci_union(v["aliases"], [v["title"]])
            v["title"], v["_named_by_canonical"] = title, True
        elif title and norm_name(title) != norm_name(v["title"]):
            v["aliases"] = ci_union(v["aliases"], [title])
    # date/place priority: a record citing sources beats the canonical-id record, which beats first-seen
    prio = 2 * bool(o.get("source_ids")) + (oid == cid)
    takes_over = prio > v["_prio"]
    d = (o.get("date") or "").strip()
    if d:
        if not v["date"] or refine_date(v["date"], d) or (takes_over and not refine_date(d, v["date"]) and d != v["date"]):
            if v["date"] and not refine_date(v["date"], d):
                note_conflict(cid, "date", d, v["date"], where(f, n))
                dn = f"Other date given: {v['date']} ({v['precision'] or '?'})."
                if dn not in v["date_note"]:
                    v["date_note"] = (v["date_note"] + " " + dn).strip()
            v["date"], v["precision"] = d, o.get("precision") or v["precision"]
        elif d != v["date"] and not refine_date(d, v["date"]):
            note_conflict(cid, "date", v["date"], d, where(f, n))
            dn = f"Other date given: {d} ({o.get('precision') or '?'})."
            if dn not in v["date_note"]:
                v["date_note"] = (v["date_note"] + " " + dn).strip()
    if not v["precision"] and o.get("precision"):
        v["precision"] = o["precision"]
    p = resolve((o.get("place_id") or "").strip())
    if p:
        if not v["place_id"]:
            v["place_id"] = p
        elif p != v["place_id"]:
            if takes_over:
                note_conflict(cid, "place_id", p, v["place_id"], where(f, n))
                v["place_id"] = p
            else:
                note_conflict(cid, "place_id", v["place_id"], p, where(f, n))
    if d or p:
        v["_prio"] = max(v["_prio"], prio)
    v["participants"] = union(v["participants"], rlist(o.get("participants")))
    v["claim_ids"] = union(v["claim_ids"], rlist(o.get("claim_ids")))
    v["source_ids"] = union(v["source_ids"], rlist(o.get("source_ids")))
    v["tags"] = union(v["tags"], o.get("tags") or [])
    dn = (o.get("date_note") or "").strip()
    if dn and dn not in v["date_note"]:
        v["date_note"] = (v["date_note"] + " " + dn).strip() if v["date_note"] else dn


STATUS_ASSERT = {}     # claim id -> (inbox, status, note) of the assertion that currently stands
STATUS_CONFLICTS = {}  # claim id -> list of {"inbox","status","note"} (all distinct assertions seen)


def inbox_name(f):
    return f.rsplit(".", 1)[0]


def merge_claim(o, f, n):
    oid = o.get("id")
    if not oid:
        problems["records without id (skipped)"].append(where(f, n))
        return
    cid = resolve(oid)
    origin[cid].append(oid)
    c = claims.get(cid)
    if c is None:
        c = claims[cid] = {
            "id": cid, "text": (o.get("text") or "").strip(), "status": o.get("status") or "",
            "said_by": o.get("said_by") or "", "podcast_refs": [], "evidence_for": [],
            "evidence_against": [], "bombshell_score": o.get("bombshell_score") or 0,
            "why_it_matters": "", "about": [], "tags": [], "joke_risk": o.get("joke_risk") or "none",
            "variant_texts": [], "notes": [], "_named_by_canonical": oid == cid,
        }
        STATUS_ASSERT[cid] = (inbox_name(f), c["status"], "base record")
    else:
        text = (o.get("text") or "").strip()
        if oid == cid and not c["_named_by_canonical"]:
            # canonical record's text/status/said_by win
            if c["text"] and norm_text(c["text"]) != norm_text(text):
                c["variant_texts"] = union(c["variant_texts"], [c["text"]])
            if o.get("status") and c["status"] and o["status"] != c["status"]:
                note_conflict(cid, "status", o["status"], c["status"], where(f, n))
            c["text"], c["_named_by_canonical"] = text or c["text"], True
            if o.get("status") and o["status"] != c["status"]:
                STATUS_ASSERT[cid] = (inbox_name(f), o["status"], "base record")
            c["status"] = o.get("status") or c["status"]
            c["said_by"] = o.get("said_by") or c["said_by"]
        else:
            if text and norm_text(text) != norm_text(c["text"]):
                c["variant_texts"] = union(c["variant_texts"], [text])
            if o.get("status") and o["status"] != c["status"]:
                note_conflict(cid, "status", c["status"], o["status"], where(f, n))
        c["bombshell_score"] = max(c["bombshell_score"] or 0, o.get("bombshell_score") or 0)
        if JOKE_ORDER.get(o.get("joke_risk") or "", 0) > JOKE_ORDER.get(c["joke_risk"], 0):
            c["joke_risk"] = o["joke_risk"]
    c["podcast_refs"] = union(c["podcast_refs"], o.get("podcast_refs") or [], key=ref_key)
    for fld in ("evidence_for", "evidence_against"):
        evs = [dict(e, source_id=resolve(e.get("source_id"))) for e in (o.get(fld) or []) if isinstance(e, dict)]
        c[fld] = union(c[fld], evs, key=ev_key)
    c["why_it_matters"] = better_summary(c["why_it_matters"], o.get("why_it_matters"))
    c["about"] = union(c["about"], rlist(o.get("about")))
    c["tags"] = union(c["tags"], o.get("tags") or [])
    if o.get("note"):
        c["notes"] = union(c["notes"], [o["note"].strip()])
    if o.get("retracted"):
        c["retracted"] = True
        c["retract_reason"] = (o.get("retract_reason") or c.get("retract_reason") or "").strip()


def merge_source(o, f, n):
    oid = o.get("id")
    if not oid:
        problems["records without id (skipped)"].append(where(f, n))
        return
    cid = resolve(oid)
    origin[cid].append(oid)
    s = sources.get(cid)
    if s is None:
        s = sources[cid] = {"id": cid, "title": "", "publisher": "", "author": "", "date": "",
                            "url": "", "tier": "", "notes": ""}
    for k in ("title", "publisher", "author", "date", "url", "tier"):
        v = (o.get(k) or "").strip()
        if v:
            if not s[k]:
                s[k] = v
            elif s[k] != v:
                note_conflict(cid, k, s[k], v, where(f, n))
    nt = (o.get("notes") or "").strip()
    if nt and nt not in s["notes"]:
        s["notes"] = (s["notes"] + " | " + nt).strip(" |")


def merge_relation(o, f, n):
    oid = o.get("id")
    frm, to = resolve(o.get("from")), resolve(o.get("to"))
    kind, kind_orig = canon_kind(o.get("kind"))
    if not (frm and to and kind):
        problems["relations missing from/to/kind (skipped)"].append(where(f, n))
        return
    # relations are identified by their (from, kind, to) triple after alias resolution
    cid = f"rel-{frm}--{kind}--{to}"
    if oid and oid != cid:
        origin[cid].append(oid)
    r = relations.get(cid)
    if r is None:
        r = relations[cid] = {"id": cid, "from": frm, "to": to, "kind": kind, "label": "",
                              "start": "", "end": "", "claim_ids": [], "source_ids": [], "labels": [],
                              "kind_original": ""}
    if kind_orig and kind_orig not in r["kind_original"].split(" | "):
        r["kind_original"] = (r["kind_original"] + " | " + kind_orig).strip(" |")
    lab = (o.get("label") or "").strip()
    if lab:
        if not r["label"]:
            r["label"] = lab
        elif norm_text(lab) != norm_text(r["label"]):
            r["labels"] = union(r["labels"], [lab])
    for k in ("start", "end"):
        v = (o.get(k) or "").strip()
        if v and not r[k]:
            r[k] = v
        elif v and v != r[k]:
            note_conflict(cid, k, r[k], v, where(f, n))
    r["claim_ids"] = union(r["claim_ids"], rlist(o.get("claim_ids")))
    r["source_ids"] = union(r["source_ids"], rlist(o.get("source_ids")))


MERGERS = {"entity": merge_entity, "event": merge_event, "claim": merge_claim,
           "source": merge_source, "relation": merge_relation}
for f, n, o in records:
    if o["op"] in MERGERS:
        MERGERS[o["op"]](o, f, n)

# ---------------------------------------------------------------- updates (after base records)
# `set` replaces scalar fields and replaces list fields wholesale (podcast_refs, about, tags, ...);
# add_* ops union. Updates naming an unknown id are collected in `orphans` and listed in the report.
orphans = []
ID_LIST_FIELDS = ("about", "location_ids", "participants", "source_ids", "claim_ids")


def set_status(c, new, f, n, note):
    """Apply a status set by an update op; two inboxes disagreeing keep the higher-evidence status."""
    cid, ib = c["id"], inbox_name(f)
    prev = STATUS_ASSERT.get(cid)
    if prev is None or prev[1] == new or prev[0] == ib:
        c["status"] = new
        STATUS_ASSERT[cid] = (ib, new, note or "update")
        return
    # routine research: a res-* inbox moving a miner/audit/official base status to an equal-or-higher-evidence
    # status is the expected outcome of research, not a conflict (the result is identical to the rule below)
    # adjudicators (the fact-check audit, the verifier, QA and lead corrections) overrule earlier calls, downgrades included
    if ib.startswith(("zx-fca", "fca", "verify", "qa", "zz-lead")):   # files apply in name order: zx-fca (audit) after verify, zz-lead last
        c["status"] = new
        STATUS_ASSERT[cid] = (ib, new, note or "update")
        return
    research = ("res-", "fc", "verify", "qa")   # inboxes whose job is to check claims (research, fact-check rounds, verifier, QA)
    if (ib.startswith(research) and prev[0].startswith(("miner-", "audit-", "official")) and cid not in STATUS_CONFLICTS
            and STATUS_RANK.get(new, 0) >= STATUS_RANK.get(prev[1], 0)):
        c["status"] = new
        STATUS_ASSERT[cid] = (ib, new, note or "update")
        return
    lst = STATUS_CONFLICTS.setdefault(cid, [])
    for a in ({"inbox": prev[0], "status": prev[1], "note": prev[2]}, {"inbox": ib, "status": new, "note": note or "update"}):
        if not any(x["inbox"] == a["inbox"] and x["status"] == a["status"] for x in lst):
            lst.append(a)
    if STATUS_RANK.get(new, 0) >= STATUS_RANK.get(prev[1], 0):  # equal rank: the later assertion wins
        c["status"] = new
        STATUS_ASSERT[cid] = (ib, new, note or "update")
    # otherwise the standing (higher-evidence) status is kept


def apply_set(tgt, st, f, n, claim=False):
    for k, v in (st or {}).items():
        if k == "id":
            continue
        if claim and k == "status":
            set_status(tgt, v, f, n, "")
            continue
        if claim and k == "retracted":
            if v:
                tgt["retracted"] = True
                tgt.setdefault("retract_reason", "")
            else:
                tgt.pop("retracted", None)
                tgt.pop("retract_reason", None)
            continue
        if k in ID_LIST_FIELDS and isinstance(v, list):
            v = rlist(v)
        elif k == "place_id":
            v = resolve(v)
        elif k in ("evidence_for", "evidence_against") and isinstance(v, list):
            v = union([], [dict(e, source_id=resolve(e.get("source_id"))) for e in v if isinstance(e, dict)], key=ev_key)
        elif k == "podcast_refs" and isinstance(v, list):
            v = list(v)
        elif k == "aliases" and isinstance(v, list):
            v = ci_union([], [a for a in v if isinstance(a, str) and a.strip()])
        elif k in ("tags", "episodes") and isinstance(v, list):
            v = union([], v)
        if k == "dates" and isinstance(v, dict) and isinstance(tgt.get("dates"), dict):
            tgt["dates"].update(v)
        else:
            tgt[k] = v


for f, n, o in records:
    op = o["op"]
    if op not in ("update_claim", "update_entity", "update_source"):
        continue
    tid = resolve(o.get("id"))
    if op == "update_claim":
        c = claims.get(tid)
        if c is None:
            orphans.append(f"{where(f, n)} update_claim {o.get('id')}")
            continue
        st = dict(o.get("set") or {})
        status_note = (o.get("note") or "").strip()
        if "status" in st:
            set_status(c, st.pop("status"), f, n, status_note)
        apply_set(c, st, f, n, claim=True)
        if c.get("retracted") and not c.get("retract_reason"):
            c["retract_reason"] = (o.get("retract_reason") or "").strip()
        for fld, add in (("evidence_for", "add_evidence_for"), ("evidence_against", "add_evidence_against")):
            evs = [dict(e, source_id=resolve(e.get("source_id"))) for e in (o.get(add) or []) if isinstance(e, dict)]
            c[fld] = union(c[fld], evs, key=ev_key)
        if o.get("add_podcast_refs"):
            c["podcast_refs"] = union(c["podcast_refs"], o["add_podcast_refs"], key=ref_key)
        if o.get("add_about"):
            c["about"] = union(c["about"], rlist(o["add_about"]))
        if o.get("add_tags"):
            c["tags"] = union(c["tags"], o["add_tags"])
        if o.get("note"):
            c["notes"] = union(c.get("notes", []), [f"[{inbox_name(f)}] {o['note'].strip()}"])
    elif op == "update_source":
        s = sources.get(tid)
        if s is None:
            orphans.append(f"{where(f, n)} update_source {o.get('id')}")
            continue
        apply_set(s, o.get("set"), f, n)
    else:
        tgt = entities.get(tid) or events.get(tid) or sources.get(tid)
        if tgt is None:
            orphans.append(f"{where(f, n)} update_entity {o.get('id')}")
            continue
        apply_set(tgt, o.get("set"), f, n)
        if o.get("add_aliases") and "aliases" in tgt:
            tgt["aliases"] = ci_union(tgt["aliases"], o["add_aliases"])
        for k in ("add_source_ids", "add_location_ids", "add_tags", "add_episodes"):
            if o.get(k):
                fld = k[4:]
                vals = rlist(o[k]) if fld.endswith("_ids") else o[k]
                tgt[fld] = union(tgt.get(fld) or [], vals)
        if o.get("add_podcast_refs") and "podcast_refs" in tgt:
            tgt["podcast_refs"] = union(tgt["podcast_refs"], o["add_podcast_refs"], key=ref_key)

# ---------------------------------------------------------------- queue (lead / conflict)
old_queue = load_json(os.path.join(KB, "queue.json"), [])
if isinstance(old_queue, dict):
    old_queue = old_queue.get("items", [])
old_by_id = {q.get("id"): q for q in old_queue if isinstance(q, dict) and q.get("id")}
queue, qseen = [], set()
for f, n, o in records:
    if o["op"] not in ("lead", "conflict"):
        continue
    text = (o.get("text") or "").strip()
    refs = o.get("refs") if o["op"] == "lead" else o.get("ids")
    refs_r = rlist(refs or []) if all(isinstance(x, str) for x in (refs or [])) else (refs or [])
    h = hashlib.sha1(json.dumps([o["op"], norm_text(text)], sort_keys=True).encode()).hexdigest()[:10]
    qid = f"q-{o['op']}-{h}"
    if qid in qseen:
        for q in queue:
            if q["id"] == qid:
                q["from"] = union(q["from"], [f.rsplit(".", 1)[0]])
                q["refs"] = union(q["refs"], refs_r)
        continue
    qseen.add(qid)
    item = {"id": qid, "kind": o["op"], "cluster": o.get("cluster", "") if o["op"] == "lead" else "",
            "text": text, "refs": refs_r, "from": [f.rsplit(".", 1)[0]], "status": "open",
            "assigned_to": "", "resolution": ""}
    prev = old_by_id.get(qid)
    if prev:
        for k, v in prev.items():
            if k not in ("id", "kind", "text", "refs", "from", "cluster"):
                item[k] = v
    queue.append(item)
# status conflicts: two inboxes set different statuses on one claim; the higher-evidence status was kept
for cid in sorted(STATUS_CONFLICTS):
    asserts = STATUS_CONFLICTS[cid]
    qid = "q-status-conflict-" + hashlib.sha1(cid.encode()).hexdigest()[:10]
    kept = claims[cid]["status"]
    text = (f"Status conflict on {cid}: " +
            "; ".join(f"{a['inbox']} says {a['status']} ({a['note'] or 'no note'})" for a in asserts) +
            f". Kept {kept} (higher evidence rank; on equal rank the later inbox wins); verify and, if needed, have a researcher set the status.")
    qseen.add(qid)
    item = {"id": qid, "kind": "status-conflict", "cluster": "", "text": text, "refs": [cid],
            "from": sorted({a["inbox"] for a in asserts}), "kept_status": kept, "assertions": asserts,
            "status": "open", "assigned_to": "", "resolution": ""}
    prev = old_by_id.get(qid)
    if prev:
        for k, v in prev.items():
            if k not in ("id", "kind", "text", "refs", "from", "cluster", "kept_status", "assertions"):
                item[k] = v
    queue.append(item)
# keep manually added queue items (not generated from inbox)
for q in old_queue:
    # status-conflict items are generated above from this run's STATUS_CONFLICTS; stale ones are dropped
    if isinstance(q, dict) and q.get("id") and q["id"] not in qseen and q.get("kind") != "status-conflict":
        queue.append(q)
# resolve ops: {queue_id, resolution, status} -> status/resolution/resolved_by on the queue item
queue_by_id = {q["id"]: q for q in queue if isinstance(q, dict) and q.get("id")}
for f, n, o in records:
    if o["op"] != "resolve":
        continue
    q = queue_by_id.get(o.get("queue_id"))
    if q is None:
        orphans.append(f"{where(f, n)} resolve {o.get('queue_id')}")
        continue
    q["status"] = o.get("status") or "resolved"
    q["resolution"] = o.get("resolution") or ""
    q["resolved_by"] = inbox_name(f)

# ---------------------------------------------------------------- finalize + sort
for coll in (entities, events, claims):
    for v in coll.values():
        v.pop("_named_by_canonical", None)
        v.pop("_prio", None)
for e in entities.values():
    e["aliases"] = [a for a in e["aliases"] if norm_name(a) != norm_name(e["name"])]
    e["episodes"] = sorted(set(x for x in e["episodes"] if isinstance(x, int)))
    e["location_ids"] = [x for x in e["location_ids"] if x != e["id"]]
for v in events.values():
    v["aliases"] = [a for a in v["aliases"] if norm_name(a) != norm_name(v["title"])]
for c in claims.values():
    c["podcast_refs"].sort(key=lambda r: (r.get("ep") or 0, r.get("t_seconds") or 0))
    if not c["variant_texts"]:
        c.pop("variant_texts")
    if not c["notes"]:
        c.pop("notes")
for r in relations.values():
    if not r["labels"]:
        r.pop("labels")
    if not r["kind_original"]:
        r.pop("kind_original")
for cid in origin:
    origin[cid] = sorted(set(x for x in origin[cid] if x != cid))


def sorted_vals(d):
    return [d[k] for k in sorted(d)]


ent_list, ev_list = sorted_vals(entities), sorted_vals(events)
cl_list, src_list, rel_list = sorted_vals(claims), sorted_vals(sources), sorted_vals(relations)

# ---------------------------------------------------------------- checks
node_ids = set(entities) | set(events)
all_ids = node_ids | set(claims) | set(sources) | set(relations)
dangling = []


def chk(owner, field, ref, allowed):
    if ref and ref not in allowed:
        dangling.append(f"{owner}.{field} -> {ref}")


for e in ent_list:
    for x in e["location_ids"]:
        chk(e["id"], "location_ids", x, node_ids)
    for x in e["source_ids"]:
        chk(e["id"], "source_ids", x, sources)
for v in ev_list:
    chk(v["id"], "place_id", v["place_id"], node_ids)
    for x in v["participants"]:
        chk(v["id"], "participants", x, node_ids)
    for x in v["claim_ids"]:
        chk(v["id"], "claim_ids", x, claims)
    for x in v["source_ids"]:
        chk(v["id"], "source_ids", x, sources)
for r in rel_list:
    chk(r["id"], "from", r["from"], node_ids)
    chk(r["id"], "to", r["to"], node_ids)
    for x in r["claim_ids"]:
        chk(r["id"], "claim_ids", x, claims)
    for x in r["source_ids"]:
        chk(r["id"], "source_ids", x, sources)
    if r["from"] == r["to"]:
        problems["self-loop relations"].append(r["id"])
for c in cl_list:
    for x in c["about"]:
        chk(c["id"], "about", x, node_ids | set(claims))
    for fld in ("evidence_for", "evidence_against"):
        for ev in c[fld]:
            chk(c["id"], fld, ev.get("source_id"), sources)

uncited = []
weak_refs = []
CONS_SECTIONS = ["ESTABLISHED without evidence_for", "REPORTED without sources",
                 "ESTABLISHED/REPORTED carried only by D-tier evidence", "CONTRADICTED without evidence_against",
                 "evidence citing a source id missing from sources.json"]
cons = {k: [] for k in CONS_SECTIONS}
for c in cl_list:
    has_pod = any(r.get("ep") and r.get("t_seconds") is not None for r in c["podcast_refs"])
    has_src = any(ev.get("source_id") in sources and sources[ev["source_id"]].get("url")
                  for ev in c["evidence_for"] + c["evidence_against"])
    if not has_pod and not has_src:
        uncited.append(f"{c['id']}: {c['text'][:90]}")
    for r in c["podcast_refs"]:
        if not (r.get("ep") and r.get("t_seconds") is not None and r.get("speaker") and r.get("quote")):
            weak_refs.append(f"{c['id']}: incomplete podcast_ref {r}")
    if c.get("retracted"):
        if not c.get("retract_reason"):
            problems["retracted claims without retract_reason"].append(c["id"])
        continue
    if c["status"] not in STATUSES:
        problems["claims with invalid status"].append(f"{c['id']}: {c['status']!r}")
    # status consistency (retracted claims are excluded)
    ev_for_ids = [ev.get("source_id") for ev in c["evidence_for"]]
    ev_all_ids = ev_for_ids + [ev.get("source_id") for ev in c["evidence_against"]]
    if c["status"] == "ESTABLISHED" and not c["evidence_for"]:
        cons["ESTABLISHED without evidence_for"].append(c["id"])
    if c["status"] == "REPORTED" and not ev_all_ids:
        cons["REPORTED without sources"].append(c["id"])
    if c["status"] in ("REPORTED", "ESTABLISHED") and ev_for_ids:
        tiers = {sources.get(i, {}).get("tier") for i in ev_for_ids}
        if not tiers - {"D", None, ""}:   # D-tier alone cannot reach REPORTED/ESTABLISHED
            cons["ESTABLISHED/REPORTED carried only by D-tier evidence"].append(
                f"{c['id']} ({c['status']}) tiers={sorted(t or '?' for t in tiers)}")
    if c["status"] == "CONTRADICTED" and not c["evidence_against"]:
        cons["CONTRADICTED without evidence_against"].append(c["id"])
    for i in sorted({i for i in ev_all_ids if i and i not in sources}):
        cons["evidence citing a source id missing from sources.json"].append(f"{c['id']} -> {i}")
for s in src_list:
    if not s["url"]:
        problems["sources without url"].append(s["id"])
    if s["tier"] not in ("A", "B", "C", "D"):
        problems["sources with invalid tier"].append(f"{s['id']}: {s['tier']!r}")
for e in ent_list:
    if e["type"] == "place" and (e["lat"] is None or e["lon"] is None):
        problems["places without lat/lon"].append(f"{e['id']} ({e['name']})")
for a, t in sorted(ALIASES.items()):
    if resolve(t) not in all_ids:
        problems["aliases pointing at unknown ids"].append(f"{a} -> {t}")

# suspected duplicates: same normalized name/alias across different ids
name_index = defaultdict(set)
for e in ent_list:
    for nm in [e["name"]] + e["aliases"]:
        k = norm_name(nm)
        if len(k) >= 3:
            name_index[k].add(e["id"])
for v in ev_list:
    for nm in [v["title"]] + v["aliases"]:
        k = norm_name(nm)
        if len(k) >= 3:
            name_index[k].add(v["id"])
# kb/not_duplicates.json: list of id groups the Curator reviewed and judged distinct
NOT_DUPS = [set(rlist(g)) for g in load_json(os.path.join(KB, "not_duplicates.json"), []) if isinstance(g, list)]
dup_names = []
for k in sorted(name_index):
    ids = name_index[k]
    # an entity of type event sharing its id with an events.json record is by design, not a duplicate
    if len(ids) > 1 and not any(ids <= g for g in NOT_DUPS):
        dup_names.append(f"'{k}': {', '.join(sorted(ids))}")

# near-identical claims on the same episode within 60 s
dup_claims = []
by_ep = defaultdict(list)
for c in cl_list:
    if c.get("retracted"):
        continue
    for r in c["podcast_refs"]:
        if r.get("ep") and r.get("t_seconds") is not None:
            by_ep[r["ep"]].append((r["t_seconds"], c["id"], norm_text(c["text"])))
seen_pairs = set()
for ep in sorted(by_ep):
    lst = sorted(set(by_ep[ep]))
    for i in range(len(lst)):
        t1, id1, x1 = lst[i]
        for j in range(i + 1, len(lst)):
            t2, id2, x2 = lst[j]
            if t2 - t1 > 60:
                break
            if id1 == id2 or (min(id1, id2), max(id1, id2)) in seen_pairs:
                continue
            w1, w2 = set(x1.split()), set(x2.split())
            jac = len(w1 & w2) / max(1, len(w1 | w2))
            ratio = difflib.SequenceMatcher(None, x1, x2).ratio()
            if ratio >= 0.72 or jac >= 0.6:
                seen_pairs.add((min(id1, id2), max(id1, id2)))
                dup_claims.append((round(max(ratio, jac), 2), ep, id1, id2))
dup_claims.sort(key=lambda x: (-x[0], x[1], x[2], x[3]))

# ---------------------------------------------------------------- write canonical files
write_json("entities.json", ent_list)
write_json("events.json", ev_list)
write_json("claims.json", cl_list)
write_json("sources.json", src_list)
write_json("relations.json", rel_list)
write_json("queue.json", queue)

# ---------------------------------------------------------------- report
L = []
L.append("Marathon Men KB merge report")
L.append(f"inbox files: {len(glob.glob(os.path.join(INBOX, '*.jsonl')))}, lines read: {len(records)}, "
         f"aliases: {len(ALIASES)}")
L.append("ops: " + ", ".join(f"{k}={v}" for k, v in sorted(op_counts.items())))
L.append("")
act_claims = [c for c in cl_list if not c.get("retracted")]
ret_claims = [c for c in cl_list if c.get("retracted")]
L.append(f"entities: {len(ent_list)}  events: {len(ev_list)}  claims: {len(cl_list)} (active {len(act_claims)}, "
         f"retracted {len(ret_claims)})  sources: {len(src_list)}  relations: {len(rel_list)}  queue: {len(queue)}")
L.append("places with geo_precision: " + ", ".join(
    f"{k or '(none)'}={v}" for k, v in sorted(Counter(e.get("geo_precision", "") for e in ent_list if e["type"] == "place").items())))
L.append("entities by type: " + ", ".join(f"{k}={v}" for k, v in sorted(Counter(e['type'] for e in ent_list).items())))
L.append("places with lat/lon: %d of %d" % (sum(1 for e in ent_list if e["type"] == "place" and e["lat"] is not None),
                                            sum(1 for e in ent_list if e["type"] == "place")))
sc = Counter(c["status"] for c in act_claims)
L.append("claims by status (active only): " + ", ".join(f"{s}={sc.get(s, 0)}" for s in STATUSES) +
         "".join(f", {k}={v}" for k, v in sorted(sc.items()) if k not in STATUSES))
L.append(f"retracted claims (excluded from status counts): {len(ret_claims)}")
L.append("claims by bombshell: " + ", ".join(f"{k}={v}" for k, v in sorted(Counter(c['bombshell_score'] for c in act_claims).items())))
L.append("sources by tier: " + ", ".join(f"{k}={v}" for k, v in sorted(Counter(s['tier'] for s in src_list).items())))
L.append("relations by kind: " + ", ".join(f"{k}={v}" for k, v in sorted(Counter(r['kind'] for r in rel_list).items(), key=lambda x: (-x[1], x[0]))))
L.append("queue: " + ", ".join(f"{k}/{s}={v}" for (k, s), v in sorted(Counter((q.get('kind'), q.get('status')) for q in queue).items())))
cl_count = Counter()
for coll in (ent_list, ev_list, act_claims):
    for x in coll:
        for t in x.get("tags", []):
            if re.fullmatch(r"c\d+", t):
                cl_count[(t, "entity" if coll is ent_list else "event" if coll is ev_list else "claim")] += 1
clusters = sorted({t for t, _ in cl_count}, key=lambda t: int(t[1:]))
L.append("by cluster (entities/events/claims):")
for t in clusters:
    L.append(f"  {t}: {cl_count[(t, 'entity')]}/{cl_count[(t, 'event')]}/{cl_count[(t, 'claim')]}")
L.append("merged ids (canonical <- variants): %d" % sum(1 for v in origin.values() if v))


def section(title, items, limit=None):
    L.append("")
    L.append(f"== {title}: {len(items)}")
    for x in (items if limit is None else items[:limit]):
        L.append("  " + x)
    if limit is not None and len(items) > limit:
        L.append(f"  ... {len(items) - limit} more")


section("dangling references", sorted(set(dangling)))
section("claims without any citation", uncited)
section("incomplete podcast refs", weak_refs, 50)
section("suspected duplicate names", dup_names)
section("suspected duplicate claims (same ep, <=60s)", [f"{s} ep{ep} {a} | {b}" for s, ep, a, b in dup_claims])
section("orphan updates (id not found; nothing applied)", orphans)
section("retracted claims", [f"{c['id']}: {c.get('retract_reason') or '(no reason)'}" for c in ret_claims])
section("status conflicts between inboxes (higher evidence kept; see queue)",
        [f"{cid}: kept {claims[cid]['status']}; " + "; ".join(f"{a['inbox']}={a['status']}" for a in STATUS_CONFLICTS[cid])
         for cid in sorted(STATUS_CONFLICTS)])
if unmapped_kinds:
    section("relation kinds not in relation_kinds.json (kept as-is)", [f"{k}: {v}" for k, v in sorted(unmapped_kinds.items())])
L.append("")
L.append("######## status consistency (retracted claims excluded)")
for k in CONS_SECTIONS:
    section(k, cons[k], 200)
for k in sorted(problems):
    section(k, problems[k], 100)
section("field conflicts while merging", field_conflicts, 200)
with open(os.path.join(KB, "report.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(L) + "\n")

summary = (f"merged: {len(ent_list)} entities, {len(ev_list)} events, {len(cl_list)} claims, "
           f"{len(src_list)} sources, {len(rel_list)} relations, {len(queue)} queue items; "
           f"dangling={len(set(dangling))} uncited={len(uncited)} dup_names={len(dup_names)} "
           f"dup_claims={len(dup_claims)}")
print(summary if "--quiet" in sys.argv else "\n".join(L[:20]) + "\n...\n" + summary)
