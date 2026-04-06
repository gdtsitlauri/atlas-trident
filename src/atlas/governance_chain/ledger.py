from __future__ import annotations

import json
import math
import sqlite3
import threading
from hashlib import sha256
from pathlib import Path

from atlas.types import Decision, ExecutionOutcome, Proposal, Vote
from atlas.utils.time_utils import utc_now_iso


class PermissionedLedger:
    """SQLite-backed append-only block ledger with permissioned voting semantics."""

    def __init__(self, db_path: str, members: list[str], quorum_ratio: float = 2 / 3) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.members = set(members)
        self.quorum_ratio = quorum_ratio
        self._lock = threading.Lock()
        self._init_db()
        for member in self.members:
            self._ensure_trust_record(member)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    height INTEGER NOT NULL,
                    previous_hash TEXT NOT NULL,
                    block_hash TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    governance_id TEXT NOT NULL,
                    action_json TEXT NOT NULL,
                    composite_score REAL NOT NULL,
                    rationale TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS votes (
                    proposal_id TEXT NOT NULL,
                    voter_id TEXT NOT NULL,
                    approve INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (proposal_id, voter_id)
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    proposal_id TEXT PRIMARY KEY,
                    approved INTEGER NOT NULL,
                    quorum_required INTEGER NOT NULL,
                    yes_votes INTEGER NOT NULL,
                    total_votes INTEGER NOT NULL,
                    consensus_latency_ms REAL NOT NULL,
                    decided_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_id TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    details TEXT NOT NULL,
                    reward REAL NOT NULL,
                    decision_latency_ms REAL NOT NULL,
                    executed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trust_scores (
                    agent_id TEXT PRIMARY KEY,
                    score REAL NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def _ensure_trust_record(self, agent_id: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT score FROM trust_scores WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO trust_scores(agent_id, score, updated_at) VALUES (?, ?, ?)",
                    (agent_id, 0.5, utc_now_iso()),
                )

    def _append_block(self, kind: str, payload: dict) -> None:
        payload_json = json.dumps(payload, sort_keys=True)
        created_at = utc_now_iso()

        with self._connect() as conn:
            last = conn.execute(
                "SELECT height, block_hash FROM blocks ORDER BY id DESC LIMIT 1"
            ).fetchone()
            height = 1 if last is None else int(last["height"]) + 1
            previous_hash = "GENESIS" if last is None else str(last["block_hash"])

            digest = sha256(
                f"{height}|{previous_hash}|{kind}|{payload_json}|{created_at}".encode("utf-8")
            ).hexdigest()

            conn.execute(
                """
                INSERT INTO blocks(height, previous_hash, block_hash, kind, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (height, previous_hash, digest, kind, payload_json, created_at),
            )

    def submit_proposal(self, proposal: Proposal) -> None:
        with self._lock:
            if proposal.governance_id not in self.members:
                raise ValueError("proposal_governance_identity_not_permitted")
            self._ensure_trust_record(proposal.agent_id)

            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO proposals(
                        proposal_id, agent_id, governance_id, action_json,
                        composite_score, rationale, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        proposal.proposal_id,
                        proposal.agent_id,
                        proposal.governance_id,
                        json.dumps(proposal.action.model_dump(), sort_keys=True),
                        proposal.composite_score,
                        proposal.rationale,
                        "pending",
                        proposal.created_at,
                    ),
                )

            self._append_block("proposal", proposal.model_dump())

    def cast_vote(self, vote: Vote) -> None:
        with self._lock:
            if vote.voter_id not in self.members:
                raise ValueError("voter_not_permitted")

            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO votes(
                        proposal_id, voter_id, approve, confidence, reason, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        vote.proposal_id,
                        vote.voter_id,
                        int(vote.approve),
                        vote.confidence,
                        vote.reason,
                        vote.created_at,
                    ),
                )

            self._append_block("vote", vote.model_dump())

    def finalize(self, proposal_id: str, consensus_latency_ms: float) -> Decision:
        with self._lock:
            with self._connect() as conn:
                vote_rows = conn.execute(
                    "SELECT approve FROM votes WHERE proposal_id = ?", (proposal_id,)
                ).fetchall()

                yes_votes = sum(int(row["approve"]) for row in vote_rows)
                total_votes = len(vote_rows)
                quorum_required = max(1, math.ceil(len(self.members) * self.quorum_ratio))
                approved = yes_votes >= quorum_required

                decision = Decision(
                    proposal_id=proposal_id,
                    approved=approved,
                    quorum_required=quorum_required,
                    yes_votes=yes_votes,
                    total_votes=total_votes,
                    consensus_latency_ms=round(consensus_latency_ms, 4),
                    decided_at=utc_now_iso(),
                )

                conn.execute(
                    """
                    INSERT OR REPLACE INTO decisions(
                        proposal_id, approved, quorum_required, yes_votes,
                        total_votes, consensus_latency_ms, decided_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        decision.proposal_id,
                        int(decision.approved),
                        decision.quorum_required,
                        decision.yes_votes,
                        decision.total_votes,
                        decision.consensus_latency_ms,
                        decision.decided_at,
                    ),
                )
                conn.execute(
                    "UPDATE proposals SET status = ? WHERE proposal_id = ?",
                    ("approved" if approved else "rejected", proposal_id),
                )

            self._append_block("decision", decision.model_dump())
            return decision

    def record_execution(self, outcome: ExecutionOutcome) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO executions(
                        proposal_id, success, details, reward,
                        decision_latency_ms, executed_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        outcome.proposal_id,
                        int(outcome.success),
                        outcome.details,
                        outcome.reward,
                        outcome.decision_latency_ms,
                        outcome.executed_at,
                    ),
                )
            self._append_block("execution", outcome.model_dump())

    def get_trust(self, agent_id: str) -> float:
        self._ensure_trust_record(agent_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT score FROM trust_scores WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            return 0.5 if row is None else float(row["score"])

    def update_trust(self, agent_id: str, delta: float) -> float:
        current = self.get_trust(agent_id)
        updated = max(0.0, min(1.0, current + delta))
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO trust_scores(agent_id, score, updated_at) VALUES (?, ?, ?)",
                (agent_id, updated, utc_now_iso()),
            )
        self._append_block("trust", {"agent_id": agent_id, "score": updated, "delta": delta})
        return updated

    def get_all_trust(self) -> dict[str, float]:
        with self._connect() as conn:
            rows = conn.execute("SELECT agent_id, score FROM trust_scores").fetchall()
            return {str(row["agent_id"]): float(row["score"]) for row in rows}

    def list_recent(self, table: str, limit: int = 50) -> list[dict]:
        if table not in {"blocks", "proposals", "votes", "decisions", "executions", "trust_scores"}:
            raise ValueError("unsupported_table")
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM {table} ORDER BY ROWID DESC LIMIT ?", (limit,)).fetchall()
            return [dict(row) for row in rows]

    def audit_consistency(self) -> dict:
        """Return consistency checks for proposal-vote-decision-execution linkage and block chain integrity."""
        with self._connect() as conn:
            orphan_votes = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM votes v
                    LEFT JOIN proposals p ON p.proposal_id = v.proposal_id
                    WHERE p.proposal_id IS NULL
                    """
                ).fetchone()[0]
            )
            orphan_decisions = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM decisions d
                    LEFT JOIN proposals p ON p.proposal_id = d.proposal_id
                    WHERE p.proposal_id IS NULL
                    """
                ).fetchone()[0]
            )
            orphan_executions = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM executions e
                    LEFT JOIN proposals p ON p.proposal_id = e.proposal_id
                    WHERE p.proposal_id IS NULL
                    """
                ).fetchone()[0]
            )
            status_mismatches = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM decisions d
                    JOIN proposals p ON p.proposal_id = d.proposal_id
                    WHERE (d.approved = 1 AND p.status != 'approved')
                       OR (d.approved = 0 AND p.status != 'rejected')
                    """
                ).fetchone()[0]
            )

            block_chain_ok = self._verify_block_chain(conn)

        checks = {
            "orphan_votes": orphan_votes,
            "orphan_decisions": orphan_decisions,
            "orphan_executions": orphan_executions,
            "status_mismatches": status_mismatches,
            "block_chain_ok": block_chain_ok,
        }
        issues: list[str] = []
        for key, value in checks.items():
            if isinstance(value, bool):
                if not value:
                    issues.append(key)
                continue
            if isinstance(value, int) and value > 0:
                issues.append(key)
        return {
            "ok": not issues,
            "checks": checks,
            "issues": issues,
        }

    def _verify_block_chain(self, conn: sqlite3.Connection) -> bool:
        rows = conn.execute(
            "SELECT height, previous_hash, block_hash, kind, payload_json, created_at FROM blocks ORDER BY height ASC"
        ).fetchall()
        previous_hash = "GENESIS"
        expected_height = 1
        for row in rows:
            height = int(row["height"])
            if height != expected_height:
                return False
            if str(row["previous_hash"]) != previous_hash:
                return False

            expected_hash = sha256(
                f"{height}|{row['previous_hash']}|{row['kind']}|{row['payload_json']}|{row['created_at']}".encode(
                    "utf-8"
                )
            ).hexdigest()
            if expected_hash != str(row["block_hash"]):
                return False

            previous_hash = str(row["block_hash"])
            expected_height += 1
        return True
