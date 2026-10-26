import os
import sys

import pytest

MCP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MCP_ROOT not in sys.path:
    sys.path.insert(0, MCP_ROOT)


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: integration tests (need test services)")
    config.addinivalue_line("markers", "e2e: end-to-end tests")


class FakeClock:
    """Deterministic replacement for the `time` module: sleep advances time."""

    def __init__(self, start=1000.0):
        self.now = start
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def strftime(self, fmt, *args):
        return "2026-01-01T00:00:00"


@pytest.fixture
def fake_clock():
    return FakeClock()
