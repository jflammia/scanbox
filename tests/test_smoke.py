"""Smoke tests to verify basic package setup."""

from scanbox import __version__


def test_version():
    assert __version__ == "0.0.1"
