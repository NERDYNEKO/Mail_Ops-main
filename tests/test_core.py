import dataclasses

import pytest

from mapster import config, contacts, followups, store
from mapster.text import clean


@pytest.fixture(autouse=True)
def tmp_cfg(tmp_path, monkeypatch):
    new = dataclasses.replace(config.cfg, db_path=tmp_path / "t.db", root=tmp_path,
                              contacts_csv=tmp_path / "c.csv", followup_templates=tmp_path / "f.json",
                              written_dir=tmp_path / "w")
    for mod in (config, store, contacts, followups):
        if hasattr(mod, "cfg"):
            monkeypatch.setattr(mod, "cfg", new)
    store.init()


def rec(**kw):
    return {"contact": {"email": "a@x.com"}, "status": "drafted", "subject": "s", "body": "b",
            "sent": [], "message_ids": [], "followups": 0, "stopped": False} | kw


def test_clean_removes_dashes_and_bangs():
    assert clean("turn-by-turn — wow!") == "turn by turn, wow."


def test_store_roundtrip_and_update():
    store.put("A@x.com", rec())
    store.update("a@x.com", status="sent", sent=["2026-01-01 10:00"])
    s = store.get("a@x.com")
    assert s["status"] == "sent" and s["sent"] == ["2026-01-01 10:00"] and s["stopped"] is False


def test_rename_moves_record():
    store.put("a@x.com", rec())
    store.rename("a@x.com", "b@x.com")
    assert store.get("a@x.com") is None and store.get("b@x.com")["contact"]["email"] == "b@x.com"


def test_contacts_roundtrip():
    contacts.upsert({"email": "a@x.com", "name": "A", "category": "client"})
    assert contacts.load()[0]["name"] == "A"
    contacts.remove("a@x.com")
    assert contacts.load() == []


def test_followups_deterministic_and_closers_last():
    c = {"email": "a@x.com", "name": "Asha Rao", "category": "client", "event": "Expo"}
    assert followups.followup_text(c, 3) == followups.followup_text(c, 3)
    pool_len = len(followups.DEFAULT_POOL["client"])
    assert followups.followup_text(c, pool_len)  # wraps without error
