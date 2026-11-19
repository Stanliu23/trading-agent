import shutil
from pathlib import Path

import keyring
import pytest
from keyring.backend import KeyringBackend

ROOT = Path(__file__).resolve().parents[1]


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.store = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        self.store.pop((service, username), None)


@pytest.fixture(autouse=True)
def memory_keyring():
    """Tests never touch the real Keychain."""
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture
def project(tmp_path):
    """A temp copy of config.yaml plus a local config with placeholder addresses."""
    shutil.copy(ROOT / "config.yaml", tmp_path / "config.yaml")
    (tmp_path / "config.local.yaml").write_text("email:\n  to: you@example.com\n  from: null\n")
    return tmp_path
