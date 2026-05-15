from typing import Any, Dict
import json
import os

class StateStore:
    """Simple JSON‑based state manager.
    
    For now we persist to a local ``state.json`` file. A Redis client can be passed
    later via the ``redis_client`` argument.
    """

    def __init__(self, storage_path: str = "state.json", redis_client: Any = None):
        self.storage_path = storage_path
        self.redis = redis_client
        self._state: Dict[str, Any] = {}
        if os.path.exists(self.storage_path):
            self.load_state()

    def save_state(self) -> None:
        """Write the in‑memory state to disk (or Redis)."""
        if self.redis:
            self.redis.set("supervisor_state", json.dumps(self._state))
        else:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)

    def load_state(self) -> None:
        """Load persisted state into memory."""
        if self.redis:
            data = self.redis.get("supervisor_state")
            if data:
                self._state = json.loads(data)
        else:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                self._state = json.load(f)

    def snapshot(self) -> Dict[str, Any]:
        """Return an immutable copy for audit/rollback."""
        return json.loads(json.dumps(self._state))

    def rollback(self, snapshot: Dict[str, Any]) -> None:
        """Replace current state with a previous snapshot and persist it."""
        self._state = snapshot
        self.save_state()

    # Helper convenience methods
    def set(self, key: str, value: Any) -> None:
        self._state[key] = value
        self.save_state()

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)
