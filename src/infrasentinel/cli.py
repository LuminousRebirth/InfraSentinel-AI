from __future__ import annotations

import argparse
import json

from .health import readiness


def main() -> int:
    parser = argparse.ArgumentParser(prog="infrasentinel")
    parser.add_argument("command", choices=["health"])
    args = parser.parse_args()

    if args.command == "health":
        result = readiness()
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        return 0 if result.status == "ready" else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
