import pytest

from src.kb import kb_store
from src.settings import settings


@pytest.fixture
def kb_data_dir(tmp_path, monkeypatch):
    kb_dir = tmp_path / "knowledge_base"
    monkeypatch.setattr(settings, "kb_data_dir", str(kb_dir))
    kb_store._base_dir_override = str(kb_dir)
    kb_store.clear()
    yield kb_dir
    kb_store.clear()


@pytest.fixture(autouse=True)
def isolated_kb(kb_data_dir):
    yield


@pytest.fixture(autouse=True)
def clear_auth(monkeypatch):
    monkeypatch.setattr(settings, "proxy_master_secret", "")
