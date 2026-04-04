# tests/unit/test_uid.py
import pytest
from src.uid import new_ulid, is_valid_ulid


@pytest.mark.unit
def test_new_ulid_is_26_chars():
    uid = new_ulid()
    assert len(uid) == 26


@pytest.mark.unit
def test_new_ulid_is_uppercase():
    uid = new_ulid()
    assert uid == uid.upper()


@pytest.mark.unit
def test_is_valid_ulid_accepts_valid():
    uid = new_ulid()
    assert is_valid_ulid(uid)


@pytest.mark.unit
def test_is_valid_ulid_rejects_short():
    assert not is_valid_ulid("TOOSHORT")


@pytest.mark.unit
def test_two_ulids_differ():
    assert new_ulid() != new_ulid()
