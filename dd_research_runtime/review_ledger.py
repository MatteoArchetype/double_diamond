"""Cycle 114: SQLite-backed, concurrency-checked append-only review receipts.

This ledger is an audit supplement, not a trusted identity provider, source authenticator,
or atomic transaction manager for an external ResearchState.
"""
import json
from contextlib import closing
import sqlite3
from hashlib import sha256
from pathlib import Path


def _hash(data):
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ReviewLedger:
    def __init__(self, path):
        self.path = str(Path(path))
        with closing(self._connect()) as db:
            db.execute("CREATE TABLE IF NOT EXISTS receipts (seq INTEGER PRIMARY KEY AUTOINCREMENT, review_digest TEXT NOT NULL UNIQUE, batch_digest TEXT NOT NULL, reviewer TEXT NOT NULL, decision TEXT NOT NULL, rationale TEXT NOT NULL, previous_hash TEXT NOT NULL, entry_hash TEXT NOT NULL)")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.execute("PRAGMA busy_timeout=5000")
        return db

    def revision(self):
        with closing(self._connect()) as db:
            return db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]

    def append(self, review, *, expected_revision):
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("expected_revision must be a nonnegative integer")
        if review.decision not in {"approved", "rejected"}:
            raise ValueError("invalid review decision")
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                result = self._append(db, review, expected_revision=expected_revision)
                db.execute("COMMIT")
                return result
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def _append(self, db, review, *, expected_revision):
        """Append on the caller's active transaction; never commit here."""
        if not db.in_transaction:
            raise RuntimeError("active transaction required")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("expected_revision must be a nonnegative integer")
        if review.decision not in {"approved", "rejected"}:
            raise ValueError("invalid review decision")
        count = db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
        if count != expected_revision:
            raise RuntimeError("stale ledger revision")
        last = db.execute("SELECT entry_hash FROM receipts ORDER BY seq DESC LIMIT 1").fetchone()
        prev = last[0] if last else "GENESIS"
        data = dict(review_digest=review.record_digest, batch_digest=review.batch_digest, reviewer=review.reviewer, decision=review.decision, rationale=review.rationale, previous_hash=prev)
        digest = _hash(data)
        db.execute("INSERT INTO receipts (review_digest,batch_digest,reviewer,decision,rationale,previous_hash,entry_hash) VALUES (?,?,?,?,?,?,?)", (review.record_digest,review.batch_digest,review.reviewer,review.decision,review.rationale,prev,digest))
        return {"revision": count+1, "entry_hash": digest}

    def verify(self):
        with closing(self._connect()) as db:
            return self._verify(db)

    def _verify(self, db):
        rows = db.execute("SELECT seq,review_digest,batch_digest,reviewer,decision,rationale,previous_hash,entry_hash FROM receipts ORDER BY seq").fetchall()
        prev = "GENESIS"
        for index, (seq, rd, bd, reviewer, decision, rationale, previous, entry) in enumerate(rows, 1):
            data = dict(review_digest=rd,batch_digest=bd,reviewer=reviewer,decision=decision,rationale=rationale,previous_hash=previous)
            if seq != index or previous != prev or _hash(data) != entry:
                return False
            prev = entry
        return True

    def receipts(self):
        with closing(self._connect()) as db:
            return db.execute("SELECT review_digest,batch_digest,reviewer,decision,entry_hash FROM receipts ORDER BY seq").fetchall()
