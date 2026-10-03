"""测试辅助：测试类未继承 unittest.TestCase 却使用了 self.assertIsNotNone，
在此注入该断言方法，避免修改测试文件本身。"""


def _assert_is_not_none(self, obj, msg=None):
    if obj is None:
        raise AssertionError(msg or "expected a non-None value, got None")


def pytest_collection_modifyitems(items):
    for item in items:
        cls = getattr(item, "cls", None)
        if cls is not None and not hasattr(cls, "assertIsNotNone"):
            cls.assertIsNotNone = _assert_is_not_none
