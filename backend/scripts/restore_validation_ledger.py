"""Verify and restore an exported ledger into a NEW isolated SQLite database."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import product_validation as validation


def restore(package, output):
    if output.exists():
        raise FileExistsError("Restore requires a new database; existing work is never overwritten")
    payload = package.get("payload")
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or validation.digest(payload) != package.get("sha256"):
        raise ValueError("Ledger schema or checksum is invalid")
    rows, revisions = payload.get("records", []), payload.get("revisions", [])
    ids = set()
    for row in rows:
        if row["id"] in ids or validation.digest(row["payload"]) != row["fingerprint"]:
            raise ValueError("Duplicate identity or corrupted record")
        ids.add(row["id"])
    for row in revisions:
        if row["record_id"] not in ids or validation.digest(json.loads(row["payload"])) != row["fingerprint"]:
            raise ValueError("Revision is corrupted or orphaned")
    prior = os.environ.get("VALIDATION_DB_PATH")
    os.environ["VALIDATION_DB_PATH"] = str(output)
    try:
        con = validation.connect()
        try:
            with con:
                for row in rows:
                    con.execute("INSERT INTO records(id,kind,project_id,payload,fingerprint,updated_at) VALUES(?,?,?,?,?,?)",
                        (row["id"], row["kind"], row["project_id"], json.dumps(row["payload"]), row["fingerprint"], row["updated_at"]))
                for row in revisions:
                    con.execute("INSERT INTO revisions(id,record_id,payload,fingerprint,saved_at) VALUES(?,?,?,?,?)",
                        tuple(row[field] for field in ("id", "record_id", "payload", "fingerprint", "saved_at")))
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Restored ledger failed integrity checking")
            return {"records": len(rows), "revisions": len(revisions), "integrity": "ok", "output": str(output), "original_unchanged": True}
        finally:
            con.close()
    finally:
        if prior is None:
            os.environ.pop("VALIDATION_DB_PATH", None)
        else:
            os.environ["VALIDATION_DB_PATH"] = prior


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(restore(json.loads(args.input.read_text(encoding="utf-8")), args.output)))
