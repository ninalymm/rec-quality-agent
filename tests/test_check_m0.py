"""验收脚本自身的单测：结果必须归一成布尔，否则统计会漏计。"""
from scripts.check_m0 import check, check_skip, results


def setup_function(_):
    results.clear()


def test_check_normalizes_list_result_to_bool():
    # `cond and [1]` 返回列表，曾被 `ok is True` 漏计，导致 26/28
    check(True and [1], "测试", "list 结果")
    assert results[0][0] is True


def test_check_normalizes_falsy_to_bool():
    check([], "测试", "空列表")
    assert results[0][0] is False


def test_check_normalizes_int_to_bool():
    check(1, "测试", "整数")
    assert results[0][0] is True


def test_check_skip_is_none():
    check_skip("测试", "跳过项")
    assert results[0][0] is None


def test_all_results_are_bool_or_none():
    check(True and [1], "测试", "a")
    check(0, "测试", "b")
    check_skip("测试", "c")
    assert all(r[0] is True or r[0] is False or r[0] is None for r in results)
