from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from .app import create_app


def create_runtime_app(
    *,
    pricing_provider_id: str,
    pricing_activate: bool,
    pricing_mode: str,
    pricing_provider_path: str | Path | None = None,
) -> FastAPI:
    provider_id = str(pricing_provider_id or "").strip()
    mode = str(pricing_mode or "").strip().lower().replace("-", "_")
    provider_path = (
        Path(pricing_provider_path).expanduser()
        if pricing_provider_path is not None
        else None
    )

    if not pricing_activate:
        raise ValueError("explicit pricing runtime requires pricing_activate=True")
    if not provider_id:
        raise ValueError("explicit pricing runtime requires pricing_provider_id")
    if mode not in {"provider_owned", "disabled"}:
        raise ValueError(f"unsupported explicit pricing mode: {mode}")
    if mode == "provider_owned":
        if provider_path is None:
            raise ValueError("provider-owned pricing runtime requires pricing_provider_path")
        if not provider_path.is_file():
            raise ValueError(f"provider-owned pricing file does not exist: {provider_path}")
    elif provider_path is not None:
        raise ValueError("disabled pricing runtime does not accept pricing_provider_path")

    return create_app(
        pricing_provider_id=provider_id,
        pricing_activate=True,
        pricing_mode=mode,
        pricing_provider_path=provider_path,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m codexchange_proxy.runtime_app",
        description="CodeXchange explicit startup application factory",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--pricing-provider-id", required=True)
    parser.add_argument("--pricing-activate", action="store_true", required=True)
    parser.add_argument(
        "--pricing-mode",
        choices=["provider_owned", "disabled"],
        required=True,
    )
    parser.add_argument("--pricing-provider-path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    application = create_runtime_app(
        pricing_provider_id=args.pricing_provider_id,
        pricing_activate=bool(args.pricing_activate),
        pricing_mode=args.pricing_mode,
        pricing_provider_path=args.pricing_provider_path,
    )
    uvicorn.run(
        application,
        host=args.host,
        port=args.port,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
