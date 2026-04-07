from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from vibecoding_board.app import create_app_from_config
from vibecoding_board.config import ConfigError, load_proxy_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the local OpenAI-compatible aggregation proxy."
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to the YAML config file. Defaults to config.yaml.",
    )
    parser.add_argument("--host", help="Override the listen host from config.")
    parser.add_argument("--port", type=int, help="Override the listen port from config.")
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug"],
        help="Uvicorn log level.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config_path = Path(args.config)

    try:
        config = load_proxy_config(config_path)
    except ConfigError as exc:
        parser.error(str(exc))

    app = create_app_from_config(config_path)
    uvicorn.run(
        app,
        host=args.host or config.listen.host,
        port=args.port or config.listen.port,
        log_level=args.log_level,
    )
    return 0
