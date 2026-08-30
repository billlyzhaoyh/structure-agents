from __future__ import annotations

from structagent_api import __version__


def test_package_exposes_expected_version() -> None:
    assert __version__ == "0.1.0"
