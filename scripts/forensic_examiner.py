"""Independent offline forensic examiner for ConsentGuard audit evidence.

Uses ONLY the Python standard library and never imports the application, so its
results do not depend on the code (or the server) under investigation. The
hash-chain check is re-implemented from the published algorithm (README §9).

    python scripts\\forensic_examiner.py acquire  --db backend\\instance\\case_study.db --out evidence\\E1 --examiner ivy
    python scripts\\forensic_examiner.py verify   evidence\\E2 [--anchor evidence\\E1]
    python scripts\\forensic_examiner.py compare  evidence\\E1 evidence\\E2
    python scripts\\forensic_examiner.py carve    evidence\\E2
    python scripts\\forensic_examiner.py timeline evidence\\E1 --out evidence\\E1_timeline.csv

Forensic principles applied:
* Acquisition is a bit-for-bit copy, hashed (SHA-256) before and after; the copy
  is only accepted if source and image hashes match, then marked read-only.
* Images are opened with SQLite ``mode=ro&immutable=1``: the examiner can never
  write to, or create journal files next to, the evidence.
* Every action that touches an image is appended to the chain-of-custody log in
  its manifest, together with a fresh hash of the image.
* An acquisition records the chain head (seq + hash) as an *anchor*. Anchors
  kept outside the system detect a full rewrite of the chain, which the
  application's own verification cannot.
"""

import argparse
import csv
import getpass
import hashlib
import json
import os
import re
import shutil
import stat
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOL = "forensic_examiner.py 1.0"
GENESIS_HASH = "0" * 64
CHAIN_VERSION = 1
IMAGE_NAME = "evidence.db"
MANIFEST_NAME = "manifest.json"
HASHED_FIELDS = ("seq", "event_id", "timestamp", "event_type", "actor_id", "subject_id", "resource_type",
                 "resource_id", "action", "outcome", "reason_code", "consent_id", "request_id", "details_json",
                 "prev_hash")
CONTENT_FIELDS = ("timestamp", "event_type", "actor_id", "subject_id", "resource_type", "resource_id", "action",
                  "outcome", "reason_code", "consent_id", "request_id", "details_json")
UUID_RE = re.compile(rb"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# --------------------------------------------------------------------------- evidence access

def open_image(path):
    """Read-only, immutable connection: SQLite will not write or lock the file."""
    uri = Path(path).resolve().as_uri() + "?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_events(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM audit_events ORDER BY seq")]


def load_users(conn):
    return {r["id"]: f"{r['username']} ({r['role']})" for r in conn.execute("SELECT id, username, role FROM users")}


def evidence_paths(directory):
    directory = Path(directory)
    image, manifest = directory / IMAGE_NAME, directory / MANIFEST_NAME
    if not image.exists() or not manifest.exists():
        sys.exit(f"{directory} is not an evidence folder (needs {IMAGE_NAME} and {MANIFEST_NAME}).")
    return image, manifest


def read_manifest(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def append_custody(manifest_path, action, examiner, details):
    manifest = read_manifest(manifest_path)
    manifest["custody"].append({"at": now_iso(), "examiner": examiner, "action": action, **details})
    Path(manifest_path).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- hash chain

def event_hash(fields):
    material = {k: fields[k] for k in HASHED_FIELDS}
    material["v"] = CHAIN_VERSION
    text = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_chain(events):
    findings, expected_prev, expected_seq = [], GENESIS_HASH, 1
    for ev in events:
        if ev["seq"] != expected_seq:
            findings.append(("SEQUENCE_GAP", ev["seq"], f"seq {expected_seq}..{ev['seq'] - 1} missing"))
        if ev["prev_hash"] != expected_prev:
            findings.append(("PREVIOUS_HASH_MISMATCH", ev["seq"], "link to preceding event broken"))
        if event_hash(ev) != ev["hash"]:
            findings.append(("HASH_MISMATCH", ev["seq"], "content does not match stored hash"))
        expected_prev, expected_seq = ev["hash"], ev["seq"] + 1
    head = events[-1] if events else None
    return {"valid": not findings, "event_count": len(events), "head_seq": head["seq"] if head else 0,
            "head_hash": head["hash"] if head else GENESIS_HASH, "findings": findings}


def dangling_references(events):
    """Event IDs that case.events_linked events say were linked, but which no longer exist."""
    present = {e["event_id"] for e in events}
    missing = []
    for ev in events:
        if ev["event_type"] == "case.events_linked":
            for eid in json.loads(ev["details_json"]).get("event_ids", []):
                if eid not in present:
                    missing.append((ev["seq"], eid))
    return missing


def check_anchor(events, anchor):
    by_seq = {e["seq"]: e for e in events}
    head = by_seq.get(anchor["head_seq"])
    if head is None:
        return (f"anchor head seq {anchor['head_seq']} no longer exists: the chain held {anchor['event_count']} "
                f"events when anchored and now holds {len(events)} (events removed and chain rewritten or truncated)")
    if head["hash"] != anchor["head_hash"]:
        return (f"seq {anchor['head_seq']} now hashes to {head['hash'][:16]}..., anchor recorded "
                f"{anchor['head_hash'][:16]}...: the chain was rewritten after the anchor was taken")
    return None


# --------------------------------------------------------------------------- SQLite record carving

def _varint(buf, pos):
    value = 0
    for i in range(9):
        if pos + i >= len(buf):
            return None, pos
        byte = buf[pos + i]
        if i == 8:
            return (value << 8) | byte, pos + 9
        value = (value << 7) | (byte & 0x7F)
        if byte < 0x80:
            return value, pos + i + 1
    return None, pos


def _serial_size(st):
    if st in (0, 8, 9):
        return 0
    if 1 <= st <= 4:
        return st
    if st == 5:
        return 6
    if st in (6, 7):
        return 8
    if st >= 12:
        return (st - 12) // 2 if st % 2 == 0 else (st - 13) // 2
    return None


def _decode(st, raw):
    if st == 0:
        return None
    if st in (8, 9):
        return st - 8
    if 1 <= st <= 6:
        return int.from_bytes(raw, "big", signed=True)
    if st >= 13 and st % 2:
        return raw.decode("utf-8")
    return raw


def carve_records(blob, columns):
    """Recover audit_events rows from raw database bytes.

    Deleted SQLite cells keep their record body (unless secure_delete is on);
    only the first 4 bytes of the cell are overwritten with freeblock metadata,
    which destroys the payload length, rowid and header-size byte. So instead
    of parsing the cell from its start, we locate each UUID and search
    backwards for a serial-type list that places a 36-byte text exactly at the
    ``event_id`` column position and decodes into a plausible event.
    """
    eid_col = columns.index("event_id")
    results = {}
    for match in UUID_RE.finditer(blob):
        pos = match.start()
        for start in range(pos - 1, max(pos - 80, 0), -1):
            types, p = [], start
            for _ in columns:
                st, p = _varint(blob, p)
                if st is None or _serial_size(st) is None:
                    break
                types.append(st)
            if len(types) != len(columns) or types[eid_col] != 13 + 2 * 36:
                continue
            offset = p + sum(_serial_size(t) for t in types[:eid_col])
            if offset != pos:
                continue
            values, q = {}, p
            try:
                for name, st in zip(columns, types):
                    size = _serial_size(st)
                    values[name] = _decode(st, blob[q:q + size])
                    q += size
            except UnicodeDecodeError:
                continue
            if isinstance(values.get("hash"), str) and len(values["hash"]) == 64 and isinstance(values.get("seq"), int):
                values["self_consistent"] = event_hash(values) == values["hash"]
                results.setdefault(values["event_id"], values)
                break
    return list(results.values())


# --------------------------------------------------------------------------- commands

def cmd_acquire(args):
    source, out = Path(args.db).resolve(), Path(args.out)
    if not source.exists():
        sys.exit(f"Source database {source} does not exist.")
    for suffix in ("-journal", "-wal"):
        if Path(str(source) + suffix).exists():
            sys.exit(f"{source.name}{suffix} exists: a write is in progress. Stop the server and retry.")
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} already contains files; evidence folders are never overwritten.")
    out.mkdir(parents=True, exist_ok=True)
    image = out / IMAGE_NAME

    before = sha256_file(source)
    shutil.copyfile(source, image)
    after, image_hash = sha256_file(source), sha256_file(image)
    if not before == after == image_hash:
        image.unlink()
        sys.exit("Source changed during acquisition (hashes differ). Stop the server and retry.")
    os.chmod(image, stat.S_IREAD)  # write-protect the image

    with open_image(image) as conn:
        chain = verify_chain(load_events(conn))
    anchor = {"head_seq": chain["head_seq"], "head_hash": chain["head_hash"], "event_count": chain["event_count"]}
    manifest = {
        "evidence_id": out.name, "tool": TOOL, "source_path": str(source), "acquired_at": now_iso(),
        "examiner": args.examiner, "note": args.note, "size_bytes": image.stat().st_size,
        "source_sha256": before, "image_sha256": image_hash, "chain_valid_at_acquisition": chain["valid"],
        "anchor": anchor,
        "custody": [{"at": now_iso(), "examiner": args.examiner, "action": "acquired", "image_sha256": image_hash}],
    }
    (out / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Acquired {source.name} -> {image} ({manifest['size_bytes']} bytes)")
    print(f"  SHA-256 source == image : {image_hash}")
    print(f"  Chain at acquisition    : {'VALID' if chain['valid'] else 'INVALID'}, {chain['event_count']} events")
    print(f"  Anchor (record externally): seq {anchor['head_seq']}  {anchor['head_hash']}")


def cmd_verify(args):
    image, manifest_path = evidence_paths(args.evidence)
    manifest = read_manifest(manifest_path)
    problems = 0

    current = sha256_file(image)
    ok = current == manifest["image_sha256"]
    problems += not ok
    print(f"[{'OK' if ok else 'FAIL'}] Evidence integrity: image SHA-256 {'matches' if ok else 'DIFFERS FROM'} "
          f"acquisition hash")

    with open_image(image) as conn:
        events = load_events(conn)
    chain = verify_chain(events)
    print(f"[{'OK' if chain['valid'] else 'FAIL'}] Internal hash chain: {chain['event_count']} events, "
          f"head seq {chain['head_seq']}")
    for kind, seq, message in chain["findings"][:20]:
        print(f"       {kind:<24} seq {seq}: {message}")
    problems += not chain["valid"]

    dangling = dangling_references(events)
    print(f"[{'OK' if not dangling else 'FAIL'}] Cross-references: "
          f"{'all linked evidence IDs present' if not dangling else f'{len(dangling)} linked event ID(s) missing'}")
    for seq, eid in dangling[:20]:
        print(f"       event seq {seq} references missing event {eid}")
    problems += bool(dangling)

    for anchor_dir in args.anchor or []:
        _, anchor_manifest = evidence_paths(anchor_dir)
        anchor = read_manifest(anchor_manifest)["anchor"]
        error = check_anchor(events, anchor)
        result = error or f"seq {anchor['head_seq']} still has hash {anchor['head_hash'][:16]}..."
        print(f"[{'OK' if not error else 'FAIL'}] External anchor from {Path(anchor_dir).name}: {result}")
        problems += bool(error)

    append_custody(manifest_path, "verified", args.examiner, {"image_sha256": current, "problems": problems})
    print("RESULT:", "NO FINDINGS" if not problems else f"{problems} CHECK(S) FAILED")
    return 1 if problems else 0


def cmd_compare(args):
    (img_a, man_a), (img_b, man_b) = evidence_paths(args.older), evidence_paths(args.newer)
    with open_image(img_a) as ca, open_image(img_b) as cb:
        old, new, users = load_events(ca), load_events(cb), load_users(ca)
    old_by_id, new_by_id = {e["event_id"]: e for e in old}, {e["event_id"]: e for e in new}

    removed = [e for e in old if e["event_id"] not in new_by_id]
    added = [e for e in new if e["event_id"] not in old_by_id]
    altered, renumbered, rehashed = [], 0, 0
    for e in old:
        n = new_by_id.get(e["event_id"])
        if n is None:
            continue
        diffs = [(f, e[f], n[f]) for f in CONTENT_FIELDS if e[f] != n[f]]
        if diffs:
            altered.append((e, diffs))
        renumbered += e["seq"] != n["seq"]
        rehashed += e["hash"] != n["hash"]

    print(f"Comparing {Path(args.older).name} ({len(old)} events) -> {Path(args.newer).name} ({len(new)} events)")
    print(f"  Removed events      : {len(removed)}")
    for e in removed:
        print(f"    seq {e['seq']:>3}  {e['timestamp']}  {e['event_type']:<18} actor {users.get(e['actor_id'], e['actor_id'])}"
              f"  {e['outcome']} {e['reason_code'] or ''}  [{e['event_id']}]")
    print(f"  Altered content     : {len(altered)}")
    for e, diffs in altered:
        for field, before, after in diffs:
            print(f"    seq {e['seq']:>3}  {field}: {before!r} -> {after!r}")
    print(f"  Renumbered (seq)    : {renumbered}")
    print(f"  Re-hashed           : {rehashed}  (a changed hash on unchanged content = chain recomputed)")
    print(f"  Added (newer only)  : {len(added)}  " + ", ".join(sorted({e['event_type'] for e in added})))
    for path in (man_a, man_b):
        append_custody(path, "compared", args.examiner, {"with": Path(img_b if path == man_a else img_a).parent.name})
    return 1 if removed or altered else 0


def cmd_carve(args):
    image, manifest_path = evidence_paths(args.evidence)
    blob = Path(image).read_bytes()
    with open_image(image) as conn:
        columns = [r["name"] for r in conn.execute("PRAGMA table_info(audit_events)")]
        live = {e["event_id"]: e for e in load_events(conn)}
        users = load_users(conn)
        free_pages = conn.execute("PRAGMA freelist_count").fetchone()[0]
    carved = carve_records(blob, columns)
    deleted = sorted((c for c in carved if c["event_id"] not in live), key=lambda c: c["seq"])
    prior = [c for c in carved if c["event_id"] in live and c["hash"] != live[c["event_id"]]["hash"]]

    print(f"Carved {Path(image).name}: {len(blob)} bytes, {free_pages} free page(s), "
          f"{len(carved)} audit record(s) found in raw bytes")
    print(f"  Deleted records recovered (not in live table): {len(deleted)}")
    for c in deleted:
        print(f"    orig seq {c['seq']:>3}  {c['timestamp']}  {c['event_type']:<15} actor "
              f"{users.get(c['actor_id'], c['actor_id'])}  {c['outcome']} {c['reason_code'] or ''}  "
              f"hash self-consistent: {'YES' if c['self_consistent'] else 'NO'}  [{c['event_id']}]")
    print(f"  Superseded versions of live records: {len(prior)}")
    if args.out:
        Path(args.out).write_text(json.dumps(deleted + prior, indent=2), encoding="utf-8")
        print(f"  Written to {args.out}")
    append_custody(manifest_path, "carved", args.examiner, {"recovered": len(deleted), "superseded": len(prior)})
    return 0


def cmd_timeline(args):
    image, manifest_path = evidence_paths(args.evidence)
    with open_image(image) as conn:
        events, users = load_events(conn), load_users(conn)
        versions = [dict(r) for r in conn.execute(
            "SELECT v.*, c.purpose, c.subject_id, c.recipient_id FROM consent_versions v "
            "JOIN consents c ON c.id = v.consent_id")]
    rows = []
    for e in events:
        details = json.loads(e["details_json"])
        rows.append({"timestamp": e["timestamp"], "source": "audit_event", "seq": e["seq"],
                     "event_id": e["event_id"], "event_type": e["event_type"],
                     "actor": users.get(e["actor_id"], e["actor_id"]), "subject": users.get(e["subject_id"], e["subject_id"]),
                     "resource": f"{e['resource_type'] or ''}:{e['resource_id'] or ''}", "action": e["action"],
                     "outcome": e["outcome"], "reason_code": e["reason_code"], "consent_id": e["consent_id"],
                     "purpose": details.get("purpose"), "category": details.get("category"), "hash": e["hash"]})
    for v in versions:
        changed = str(v["changed_at"]).replace(" ", "T")
        rows.append({"timestamp": changed if changed.endswith("Z") else changed + "Z", "source": "consent_history",
                     "event_type": f"consent.v{v['version']}.{v['change_type']}",
                     "actor": users.get(v["changed_by"], "system"), "subject": users.get(v["subject_id"]),
                     "resource": f"consent:{v['consent_id']}", "outcome": v["status"], "consent_id": v["consent_id"],
                     "purpose": v["purpose"], "category": v["categories"]})
    rows.sort(key=lambda r: (r["timestamp"], r["source"] != "consent_history", r.get("seq") or 0))
    fields = ["timestamp", "source", "seq", "event_id", "event_type", "actor", "subject", "resource", "action",
              "outcome", "reason_code", "consent_id", "purpose", "category", "hash"]
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    append_custody(manifest_path, "timeline_exported", args.examiner, {"rows": len(rows)})
    print(f"Wrote {len(rows)} timeline rows to {args.out}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--examiner", default=getpass.getuser(), help="name recorded in the custody log")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("acquire", parents=[common], help="bit-for-bit, hash-verified copy of a database")
    p.add_argument("--db", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--note", default="")
    p = sub.add_parser("verify", parents=[common],
                       help="evidence hash, internal chain, cross-references, external anchors")
    p.add_argument("evidence")
    p.add_argument("--anchor", action="append", help="earlier evidence folder whose anchor must still hold")
    p = sub.add_parser("compare", parents=[common], help="diff two acquisitions by event ID")
    p.add_argument("older")
    p.add_argument("newer")
    p = sub.add_parser("carve", parents=[common], help="recover deleted audit records from raw database bytes")
    p.add_argument("evidence")
    p.add_argument("--out")
    p = sub.add_parser("timeline", parents=[common], help="export a merged timeline CSV")
    p.add_argument("evidence")
    p.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    handler = {"acquire": cmd_acquire, "verify": cmd_verify, "compare": cmd_compare, "carve": cmd_carve,
               "timeline": cmd_timeline}[args.command]
    return handler(args) or 0


if __name__ == "__main__":
    sys.exit(main())
