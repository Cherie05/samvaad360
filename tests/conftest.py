"""Isolated synthetic fixtures: tests never touch the interactive demo database."""

import pytest

@pytest.fixture
def service(tmp_path):
    from samvaad.service import LocalService

    return LocalService(db_path=tmp_path / "acceptance.sqlite3")


@pytest.fixture
def analyst(service):
    return service.resolve_actor("meera")


@pytest.fixture
def manager(service):
    return service.resolve_actor("arjun")


@pytest.fixture
def credit(service):
    return service.resolve_actor("kavya")


@pytest.fixture
def runner(service):
    return service.resolve_actor("local-runner")


@pytest.fixture
def admin(service):
    return service.resolve_actor("demo-admin")


@pytest.fixture
def queued_retention(service, analyst):
    return service.recommend("C0002", analyst)


@pytest.fixture
def queued_topup(service, analyst):
    return service.recommend("C0003", analyst)
