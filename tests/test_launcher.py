import io
import json
from unittest.mock import Mock

import pytest

from scripts import launch_app


@pytest.mark.parametrize('payload,expected', [
    ({'info': {'title': 'Dhan Turnover Scanner'}}, True),
    ({'info': {'title': 'Different application'}}, False),
    ([], False), ({'info': []}, False), ({'info': None}, False), (None, False),
])
def test_launcher_checks_server_identity_without_crashing(monkeypatch, payload, expected):
    opener = Mock()
    opener.open.return_value = io.StringIO(json.dumps(payload))
    monkeypatch.setattr(launch_app.urllib.request, 'build_opener', lambda *_: opener)
    assert launch_app.app_ready('http://unused.test') is expected


def test_launcher_unresponsive_server_is_not_ready(monkeypatch):
    opener = Mock()
    opener.open.side_effect = TimeoutError('test timeout')
    monkeypatch.setattr(launch_app.urllib.request, 'build_opener', lambda *_: opener)
    assert not launch_app.app_ready('http://unused.test')
