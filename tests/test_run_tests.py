#!/usr/bin/env python
"""
测试运行器
统一管理和运行所有测试
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_single_test(test_file):
    """运行单个测试文件"""
    print(f"\n{'='*60}")
    print(f"运行测试: {test_file}")
    print(f"{'='*60}")

    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent / test_file)],
            capture_output=False,
            check=False,
        )

        return result.returncode == 0
    except Exception as e:
        print(f"运行测试失败: {e}")
        return False


def run_all_tests():
    """运行所有测试"""
    test_files = [
        "test_redis_integration.py",
        "test_passorder.py",
        "test_concurrent_trading.py",
        "test_stress_trading.py",
        "test_auto_cancel.py",
        "test_order_timeout.py",
        "test_constants.py",
        "test_status_logic_fix.py",
        "test_notification_fix.py",
    ]

    print("QMT 交易系统测试套件")
    print("=" * 60)

    results = {}
    for test_file in test_files:
        test_path = Path(__file__).parent / test_file
        if test_path.exists():
            success = run_single_test(test_file)
            results[test_file] = success
        else:
            print(f"警告: 测试文件不存在 - {test_file}")
            results[test_file] = False

    # 打印测试结果汇总
    print(f"\n{'='*60}")
    print("测试结果汇总")
    print(f"{'='*60}")

    success_count = 0
    for test_file, success in results.items():
        status = "√ 通过" if success else "× 失败"
        print(f"{status:>8} - {test_file}")
        if success:
            success_count += 1

    total_tests = len(results)
    print(f"\n总计: {success_count}/{total_tests} 通过")

    if success_count == total_tests:
        print("✅ 所有测试通过!")
        return True
    else:
        print("❌ 部分测试失败，请检查日志")
        return False


def run_pytest():
    """使用 pytest 运行测试"""
    try:
        import pytest

        print("使用 pytest 运行测试...")

        # pytest 参数
        pytest_args = [
            str(Path(__file__).parent),
            "-v",  # 详细输出
            "--tb=short",  # 简短回溯
            "--color=yes",  # 彩色输出
        ]

        result = pytest.main(pytest_args)
        return result == 0

    except ImportError:
        print("pytest 未安装，请运行: pip install pytest")
        return False


def main():
    parser = argparse.ArgumentParser(description="QMT 交易系统测试运行器")
    parser.add_argument("--test", "-t", help="运行指定的测试文件")
    parser.add_argument("--pytest", action="store_true", help="使用 pytest 运行测试")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有可用的测试文件")

    args = parser.parse_args()

    if args.list:
        # 列出所有测试文件
        print("可用的测试文件:")
        test_dir = Path(__file__).parent
        for test_file in sorted(test_dir.glob("test_*.py")):
            print(f"  - {test_file.name}")
        return

    if args.test:
        # 运行指定测试
        success = run_single_test(args.test)
        sys.exit(0 if success else 1)

    if args.pytest:
        # 使用 pytest
        success = run_pytest()
        sys.exit(0 if success else 1)

    # 默认运行所有测试
    success = run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
