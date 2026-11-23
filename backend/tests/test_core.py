"""Logic that needs no database: permission lattice, JWT verification, extractive answering, API auth gates."""
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core import auth
from app.core.acl import ALL_ROLES, CLASSIFICATIONS, PERMISSION_MATRIX, can_read, can_upload, roles_for_classification
from app.core.config import settings
from app.services.answer import FALLBACK, build_answer, coverage, is_supported
from app.services.embeddings import HashEmbedder


# ---------------------------------------------------------------- permission lattice
def test_lattice_truth_table_20_cases():
    expected = {
        "Public": {"employee", "manager", "hr", "admin"}, "General_Internal": {"employee", "manager", "hr", "admin"},
        "Management": {"manager", "admin"}, "HR_Confidential": {"hr", "admin"}, "Restricted": {"admin"},
    }
    for c in CLASSIFICATIONS:
        for r in ALL_ROLES:
            assert can_read(r, c) is (r in expected[c]), (c, r)
    assert PERMISSION_MATRIX["Management"].isdisjoint({"hr", "employee"})


def test_unknown_classification_fails_closed():
    with pytest.raises(ValueError):
        roles_for_classification("Top_Secret")
    assert can_read("admin", "Top_Secret") is False


def test_delegated_upload_rules():
    assert not any(can_upload("employee", c) for c in CLASSIFICATIONS)
    assert can_upload("manager", "Management") and not can_upload("manager", "HR_Confidential")
    assert can_upload("hr", "HR_Confidential") and not can_upload("hr", "Management")
    assert all(can_upload("admin", c) for c in CLASSIFICATIONS)


# ---------------------------------------------------------------- JWT verification
SECRET = "x" * 48


def _token(**over):
    claims = {"sub": "11111111-1111-1111-1111-111111111111", "aud": "authenticated", "exp": int(time.time()) + 60, **over}
    return jwt.encode(claims, SECRET, algorithm="HS256")


def test_decode_valid_and_rejects_bad(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    assert auth.decode_token(_token())["sub"].startswith("1111")
    with pytest.raises(jwt.PyJWTError):
        auth.decode_token(_token(exp=int(time.time()) - 5))  # expired
    with pytest.raises(jwt.PyJWTError):
        auth.decode_token(_token(aud="anon"))  # wrong audience
    with pytest.raises(jwt.PyJWTError):
        auth.decode_token(jwt.encode({"sub": "a", "aud": "authenticated", "exp": int(time.time()) + 60}, "y" * 48, algorithm="HS256"))
    unsigned = jwt.encode({"sub": "a", "aud": "authenticated", "exp": int(time.time()) + 60}, None, algorithm="none")
    with pytest.raises(jwt.PyJWTError):
        auth.decode_token(unsigned)  # alg=none is never accepted


def test_hs256_refused_without_configured_secret(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", "")
    with pytest.raises(jwt.PyJWTError):
        auth.decode_token(_token())


def test_protected_routes_require_token():
    from app.main import app

    c = TestClient(app)
    for method, path in [("get", "/api/v1/me"), ("get", "/api/v1/documents"), ("post", "/api/v1/chat/query"),
                         ("get", "/api/v1/admin/users"), ("get", "/api/v1/admin/audit/verify"),
                         ("post", "/api/v1/admin/security-check"), ("delete", "/api/v1/documents/abc")]:
        r = getattr(c, method)(path, **({"json": {"query": "hello there"}} if method == "post" else {}))
        assert r.status_code == 401, (path, r.status_code)
    r = c.get("/api/v1/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


# ---------------------------------------------------------------- extractive answering
def hit(content, dense=0.7, kind="text", title="Leave Policy", page=1, section="Leave", cls="General_Internal"):
    return dict(chunk_id="00000000-0000-0000-0000-000000000001", document_id="00000000-0000-0000-0000-0000000000aa",
                title=title, page=page, section=section, kind=kind, content=content, classification=cls,
                dense_score=dense, lexical_score=0.2, rrf_score=0.03)


def test_answer_cites_supporting_sentence_only():
    h = hit("Full-time employees receive 24 days of paid annual leave per calendar year. Leave requests need 3 days notice.")
    a = build_answer("How many annual leave days do employees get?", [h])
    assert a.mode == "extractive_answer" and "24 days" in a.text and "[C1]" in a.text
    assert a.sources[0]["page"] == 1 and a.sources[0]["classification"] == "General_Internal"


def test_fallback_when_unsupported_or_low_score():
    off = hit("Core collaboration hours are 10:00 to 16:00 India Standard Time.", dense=0.4)
    assert build_answer("Who won the football world cup in 2022?", [off]).text == FALLBACK
    assert build_answer("What is the salary band for Grade G7?", []).mode == "fallback"


def test_exact_identifier_passes_even_with_weak_dense_score():
    h = hit("Policy HR-402 sets the target bonus for Grade G7 at 10 percent of base salary.", dense=0.3)
    assert is_supported("Policy HR-402 Grade G7 bonus", h)


def test_table_answer_returns_header_and_matching_row():
    t = hit("| Grade | Min | Max |\n| --- | --- | --- |\n| G6 | 900000 | 1200000 |\n| G7 | 1200000 | 1800000 |",
            kind="table", section="Bands")
    a = build_answer("What is the salary Min and Max for Grade G7?", [t])
    assert "| G7 | 1200000 | 1800000 |" in a.text and "| Grade | Min | Max |" in a.text and "G6" not in a.text


def test_hash_embedder_is_deterministic_and_normalised():
    e = HashEmbedder()
    v1, v2 = e.embed_query("annual leave days"), e.embed_query("annual leave days")
    assert v1 == v2 and len(v1) == 384 and abs(sum(x * x for x in v1) - 1) < 1e-4
    assert coverage("annual leave", "employees get annual leave") == 1.0


def test_answer_skips_duplicate_sentences_but_keeps_different_numbers():
    from app.services.answer import build_answer

    def hit(i, text):
        return dict(chunk_id=i, document_id=i, title=f"d{i}", page=1, section="", kind="text", content=text,
                    classification="Public", dense_score=0.9, lexical_score=0.5)

    q = "How many days of annual leave do employees get?"
    a = build_answer(q, [hit(1, "Employees receive 24 days of annual leave. " * 3),
                         hit(2, "Employees receive 24 days of annual leave."),
                         hit(3, "Grade B employees receive 28 days of annual leave.")])
    assert a.text.count("24 days") == 1
    assert "28 days" in a.text
