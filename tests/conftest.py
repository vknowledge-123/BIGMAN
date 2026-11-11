"""Legacy strategy tests run as an admin; account tests exercise real authentication.

These dependency overrides exist only in pytest, never in the application.
"""
import pytest


def pytest_configure(config):
    config.addinivalue_line('markers', 'real_auth: exercise production authentication dependencies')


@pytest.fixture(autouse=True)
def legacy_admin_session(request, monkeypatch):
    from app import security
    monkeypatch.setattr(security, 'limits', security.RequestLimits())
    if request.node.get_closest_marker('real_auth'):
        yield
        return
    monkeypatch.setattr(security, 'transport', lambda request: None)
    monkeypatch.setattr(security, 'authorize_upload', lambda request: None)
    from app import access, main
    from app.accounts import DisplaySettings
    user = dict(id='test-admin', name='Test Admin', email='admin@example.com',
                role='admin', status='active', csrf='test-csrf')

    class Preferences:
        settings = DisplaySettings(circuit_enabled='circuit_band_browser' in request.node.nodeid)
        revision = 0

        def display(self, settings=None):
            if settings is not None:
                self.settings = settings
                self.revision += 1
            return dict(settings=self.settings.model_dump(), revision=self.revision)

        def users(self):
            return []

    old = main.app.dependency_overrides.copy()
    for dependency in (access.require_admin, access.require_user, access.optional_user):
        main.app.dependency_overrides[dependency] = lambda: user
    monkeypatch.setattr(access, 'accounts', Preferences())
    try:
        yield
    finally:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(old)
