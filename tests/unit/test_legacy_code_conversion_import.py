import pytest


@pytest.mark.unit
def test_legacy_redis_signal_sender_import_available():
    from redis_signal_sender import jq_to_qmt_code, qmt_to_jq_code

    assert callable(jq_to_qmt_code)
    assert callable(qmt_to_jq_code)
