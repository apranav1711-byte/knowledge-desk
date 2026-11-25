"""Local SQLite store: role pre-filtering, re-classification trigger, append-only hash-chained audit log."""
import asyncio
import json
import sqlite3

import pytest

from app.core import db as dbmod
from app.core.acl import roles_for_classification
from app.services.embeddings import HashEmbedder

T = dbmod.DEFAULT_TENANT


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod.settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dbmod.settings, "DATABASE_PATH", tmp_path / "t.db")
    monkeypatch.setattr(dbmod, "_db", None)
    d = asyncio.run(dbmod.init_pool())
    yield d
    asyncio.run(dbmod.close_pool())


def _doc(d, cls, text):
    e = HashEmbedder()
    doc = dbmod.new_id()
    ts = dbmod.now()

    async def go():
        await d.execute("insert into documents (id, tenant_id, title, filename, file_type, file_size, checksum, "
                        "classification, status, created_at, updated_at) values (?,?,?,?,?,?,?,?,'ready',?,?)",
                        doc, T, cls, cls + ".txt", "txt", 1, doc, cls, ts, ts)
        await d.execute("insert into chunks (id, document_id, tenant_id, chunk_index, content, classification, "
                        "allowed_roles, embedding) values (?,?,?,?,?,?,?,?)", dbmod.new_id(), doc, T, 0, text, cls,
                        json.dumps(roles_for_classification(cls)), dbmod.vec(e.embed_passages([text])[0]))
    asyncio.run(go())
    return doc


def _search(d, q, role):
    qv = HashEmbedder().embed_query(q)
    return asyncio.run(d.match_chunks(qv, q, T, [role], 10))


def test_role_prefilter_never_returns_unreadable_chunks(db):
    _doc(db, "Public", "cafeteria opens at eight")
    _doc(db, "Management", "salary budget for managers is confidential")
    _doc(db, "HR_Confidential", "salary disciplinary records for staff")
    seen = {r: {h["classification"] for h in _search(db, "salary budget records cafeteria", r)}
            for r in ("employee", "manager", "hr", "admin")}
    assert seen["employee"] == {"Public"}
    assert seen["manager"] == {"Public", "Management"}
    assert seen["hr"] == {"Public", "HR_Confidential"}
    assert seen["admin"] == {"Public", "Management", "HR_Confidential"}


def test_reclassification_relabels_chunks(db):
    doc = _doc(db, "Public", "parking passes cost nine hundred")
    assert _search(db, "parking passes", "employee")
    asyncio.run(db.execute("update documents set classification='Restricted' where id=?", doc))
    assert not _search(db, "parking passes", "employee")
    assert _search(db, "parking passes", "admin")[0]["classification"] == "Restricted"


def test_audit_chain_is_append_only_and_detects_tampering(db):
    for i in range(3):
        asyncio.run(db.append_audit(T, None, "a@b.c", "admin", "query", f"q{i}", "ans", "fallback", [], 0.1, 5, {"i": i}))
    assert asyncio.run(db.verify_audit(T))["valid"] is True
    with pytest.raises(sqlite3.DatabaseError):
        asyncio.run(db.execute("update audit_logs set query='forged' where seq=2"))
    with pytest.raises(sqlite3.DatabaseError):
        asyncio.run(db.execute("delete from audit_logs where seq=3"))
    # bypass the triggers the way an attacker with file access could, and the chain check still catches it
    asyncio.run(db.execute("drop trigger audit_logs_no_update"))
    asyncio.run(db.execute("update audit_logs set query='forged' where seq=2"))
    r = asyncio.run(db.verify_audit(T))
    assert r["valid"] is False and r["broken_seq"] == 2
