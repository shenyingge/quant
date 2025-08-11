"""
测试股票代码格式转换
"""

from redis_signal_sender import jq_to_qmt_code, qmt_to_jq_code


def test_code_conversion():
    """测试代码转换函数"""

    # 测试聚宽到QMT的转换
    print("=== 测试聚宽 -> QMT 转换 ===")
    test_cases_jq = [
        ("000001.XSHE", "000001.SZ"),  # 深圳平安银行
        ("600000.XSHG", "600000.SH"),  # 上海浦发银行
        ("000002.XSHE", "000002.SZ"),  # 深圳万科A
        ("600036.XSHG", "600036.SH"),  # 上海招商银行
        ("300750.XSHE", "300750.SZ"),  # 创业板
        ("688001.XSHG", "688001.SH"),  # 科创板
    ]

    for jq_code, expected_qmt in test_cases_jq:
        result = jq_to_qmt_code(jq_code)
        status = "OK" if result == expected_qmt else "FAIL"
        print(f"{status} {jq_code} -> {result} (expected: {expected_qmt})")

    print("\n=== 测试 QMT -> 聚宽 转换 ===")
    test_cases_qmt = [
        ("000001.SZ", "000001.XSHE"),  # 深圳平安银行
        ("600000.SH", "600000.XSHG"),  # 上海浦发银行
        ("000002.SZ", "000002.XSHE"),  # 深圳万科A
        ("600036.SH", "600036.XSHG"),  # 上海招商银行
        ("300750.SZ", "300750.XSHE"),  # 创业板
        ("688001.SH", "688001.XSHG"),  # 科创板
    ]

    for qmt_code, expected_jq in test_cases_qmt:
        result = qmt_to_jq_code(qmt_code)
        status = "OK" if result == expected_jq else "FAIL"
        print(f"{status} {qmt_code} -> {result} (expected: {expected_jq})")

    print("\n=== 测试边界情况 ===")
    edge_cases = [
        (None, None),
        ("", ""),
        ("000001", "000001"),  # 没有交易所后缀
        ("INVALID.XXX", "INVALID.XXX"),  # 未知交易所
    ]

    for input_code, expected in edge_cases:
        result_jq_to_qmt = jq_to_qmt_code(input_code)
        result_qmt_to_jq = qmt_to_jq_code(input_code)
        print(f"输入: {input_code}")
        print(f"  jq_to_qmt: {result_jq_to_qmt}")
        print(f"  qmt_to_jq: {result_qmt_to_jq}")

    print("\n=== 测试往返转换 ===")
    test_codes = ["000001.XSHE", "600000.XSHG", "300750.XSHE"]
    for jq_code in test_codes:
        qmt_code = jq_to_qmt_code(jq_code)
        back_to_jq = qmt_to_jq_code(qmt_code)
        status = "OK" if back_to_jq == jq_code else "FAIL"
        print(f"{status} {jq_code} -> {qmt_code} -> {back_to_jq}")


if __name__ == "__main__":
    test_code_conversion()
    print("\n测试完成！")
