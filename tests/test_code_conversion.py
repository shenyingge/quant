from redis_signal_sender import jq_to_qmt_code, qmt_to_jq_code


def test_jq_to_qmt_code_basic_cases():
    assert jq_to_qmt_code("000001.XSHE") == "000001.SZ"
    assert jq_to_qmt_code("600000.XSHG") == "600000.SH"


def test_qmt_to_jq_code_basic_cases():
    assert qmt_to_jq_code("000001.SZ") == "000001.XSHE"
    assert qmt_to_jq_code("600000.SH") == "600000.XSHG"


def test_code_conversion_edge_cases():
    assert jq_to_qmt_code(None) is None
    assert qmt_to_jq_code(None) is None
    assert jq_to_qmt_code("") == ""
    assert qmt_to_jq_code("") == ""
    assert jq_to_qmt_code("000001") == "000001"
    assert qmt_to_jq_code("000001") == "000001"
    assert jq_to_qmt_code("INVALID.XXX") == "INVALID.XXX"
    assert qmt_to_jq_code("INVALID.XXX") == "INVALID.XXX"


def test_round_trip_conversion():
    original = "300750.XSHE"
    assert qmt_to_jq_code(jq_to_qmt_code(original)) == original
