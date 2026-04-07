from __future__ import annotations

from pathlib import Path
import tempfile

from vibecoding_board.config import ProxyConfig, dump_proxy_config, load_proxy_config


class ConfigStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()

    def load(self) -> ProxyConfig:
        return load_proxy_config(self.path)

    def save(self, config: ProxyConfig) -> None:
        serialized = dump_proxy_config(config)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=f"{self.path.stem}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(serialized)
            temp_path = Path(handle.name)

        temp_path.replace(self.path)
