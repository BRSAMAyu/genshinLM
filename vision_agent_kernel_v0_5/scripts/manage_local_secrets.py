"""Manage Aurora local development secrets."""
from __future__ import annotations

import argparse
import getpass
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.local_secret_store import LocalSecretStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Aurora local secrets")
    sub = parser.add_subparsers(dest="cmd", required=True)
    set_cmd = sub.add_parser("set")
    set_cmd.add_argument("name")
    set_cmd.add_argument("--value", default=None)
    get_cmd = sub.add_parser("check")
    get_cmd.add_argument("name")
    del_cmd = sub.add_parser("delete")
    del_cmd.add_argument("name")
    args = parser.parse_args()

    store = LocalSecretStore()
    if args.cmd == "set":
        value = args.value or getpass.getpass(f"{args.name}: ")
        store.set(args.name, value)
        print(f"stored {args.name} at {store.path}")
        return 0
    if args.cmd == "check":
        value = store.get(args.name)
        print(f"{args.name}: {'present' if value else 'missing'}")
        return 0 if value else 1
    if args.cmd == "delete":
        print(f"{args.name}: {'deleted' if store.delete(args.name) else 'missing'}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
