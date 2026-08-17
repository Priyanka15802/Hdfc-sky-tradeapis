from __future__ import annotations

import json
import os
import stat
from pathlib import Path


class SessionStore:
    """Persists the access/refresh token locally so you don't have to
    re-run the full 6-step login on every process restart.

    The file is chmod'd 600 and is already covered by .gitignore — never
    commit it, it is as sensitive as a password.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def save(self, data: dict) -> None:
        self.path.write_text(json.dumps(data))
        os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text())

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
