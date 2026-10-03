"""Test fixtures: the test classes use unittest-style assertions without
inheriting from unittest.TestCase, so provide them here."""

import pytest


def _assertIsNotNone(self, obj, msg=None):
    if obj is None:
        raise AssertionError(msg or "unexpectedly None")


def _assertIsNone(self, obj, msg=None):
    if obj is not None:
        raise AssertionError(msg or f"unexpectedly not None: {obj!r}")


def _assertTrue(self, expr, msg=None):
    if not expr:
        raise AssertionError(msg or f"{expr!r} is not true")


def _assertEqual(self, first, second, msg=None):
    if first != second:
        raise AssertionError(msg or f"{first!r} != {second!r}")


@pytest.fixture(autouse=True)
def _unittest_assertions(request):
    cls = getattr(request, "cls", None)
    if cls is None:
        return
    for name, fn in [("assertIsNotNone", _assertIsNotNone),
                     ("assertIsNone", _assertIsNone),
                     ("assertTrue", _assertTrue),
                     ("assertEqual", _assertEqual)]:
        if not hasattr(cls, name):
            setattr(cls, name, fn)
