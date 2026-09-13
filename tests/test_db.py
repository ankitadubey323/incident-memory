"""Tests for the DynamoDB access layer — one test per access pattern."""
import pytest


def test_record_incident_writes_keys_and_counter(db):
    inc = db.record_incident("checkout", "sev2", "503 on /pay")

    assert inc["PK"] == "SERVICE#checkout"
    assert inc["SK"].startswith("INCIDENT#")
    assert inc["GSI1PK"] == "STATUS#open"
    assert inc["status"] == "open"
    assert inc["incident_id"] == f"checkout|{inc['SK']}"

    stats = db.service_stats("checkout")
    assert stats["incident_count"] == 1
    assert stats["last_incident_at"] == inc["created_at"]


def test_counter_increments_atomically(db):
    for _ in range(3):
        db.record_incident("checkout", "sev3", "x")
    assert db.service_stats("checkout")["incident_count"] == 3


def test_find_similar_newest_first_and_keyword_filter(db):
    a = db.record_incident("checkout", "sev2", "503 errors on /pay")
    b = db.record_incident("checkout", "sev3", "slow redis replies")
    db.record_incident("other-svc", "sev1", "503 somewhere else")  # different partition

    all_items = db.find_similar("checkout")
    assert [i["incident_id"] for i in all_items] == [b["incident_id"], a["incident_id"]]

    only_503 = db.find_similar("checkout", keyword="503")
    assert [i["incident_id"] for i in only_503] == [a["incident_id"]]

    assert db.find_similar("checkout", limit=1) == [all_items[0]]


def test_get_incident_roundtrip(db):
    inc = db.record_incident("checkout", "sev2", "503 on /pay")
    fetched = db.get_incident(inc["incident_id"])
    assert fetched["summary"] == "503 on /pay"
    assert db.get_incident("checkout|INCIDENT#nope") is None


def test_list_open_uses_gsi_and_excludes_resolved(db):
    a = db.record_incident("checkout", "sev2", "a")
    b = db.record_incident("payments", "sev1", "b")
    db.resolve_incident(a["incident_id"], "rc", "fix")

    open_ids = {i["incident_id"] for i in db.list_open()}
    assert open_ids == {b["incident_id"]}


def test_resolve_is_conditional(db):
    inc = db.record_incident("checkout", "sev2", "503")

    resolved = db.resolve_incident(inc["incident_id"], "pool exhausted", "raise maxclients")
    assert resolved["status"] == "resolved"
    assert resolved["GSI1PK"] == "STATUS#resolved"
    assert resolved["fix"] == "raise maxclients"
    assert "resolved_at" in resolved

    with pytest.raises(ValueError, match="not open"):
        db.resolve_incident(inc["incident_id"], "again", "again")


def test_notes_have_ttl_and_are_listed_per_service(db):
    note = db.add_note("checkout", "check redis first", author="alice", ttl_days=7)
    assert note["SK"].startswith("NOTE#")
    assert isinstance(note["expires_at"], int)

    notes = db.list_notes("checkout")
    assert len(notes) == 1 and notes[0]["note"] == "check redis first"
    assert db.list_notes("payments") == []


def test_service_stats_for_unknown_service(db):
    assert db.service_stats("ghost") == {
        "service": "ghost", "incident_count": 0, "last_incident_at": None,
    }
