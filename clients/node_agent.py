"""MedChain hospital node agent — a deployable, self-contained federated participant.

A hospital runs this on its own infrastructure, pointing at its OWN local CSV. The agent
logs in, and either participates in one round (`participate`) or watches for open rounds and
auto-participates (`watch`). Raw data never leaves the machine — only the trained weight
vector and measured metrics are submitted.

Configuration is via environment variables (or flags):

    MEDCHAIN_API           backend base URL           (default http://127.0.0.1:8000)
    MEDCHAIN_EMAIL         node account email         (required)
    MEDCHAIN_PASSWORD      node account password      (required)
    MEDCHAIN_HOSPITAL_ID   this hospital's id         (required)
    MEDCHAIN_OBJECTIVE_ID  objective to train for     (required for CSV mode)
    MEDCHAIN_CSV_PATH      path to the local CSV      (required for CSV mode)
    MEDCHAIN_NODE_INDEX    local split seed offset    (default 0)
    MEDCHAIN_POLL_SECONDS  watch poll interval        (default 10)

Usage:
    python clients/node_agent.py participate
    python clients/node_agent.py watch
"""

from __future__ import annotations

import argparse
import os
import time

import requests

from hospital_client import login, participate


def _cfg(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def _require(value: str | None, name: str) -> str:
    if not value:
        raise SystemExit(f"{name} is required (set the env var or pass the flag)")
    return value


def _open_round_for(api: str, token: str, hospital_id: str) -> dict | None:
    response = requests.get(
        f"{api}/rounds", headers={"Authorization": f"Bearer {token}"}, timeout=30
    )
    response.raise_for_status()
    for training_round in sorted(response.json(), key=lambda r: r["round_number"], reverse=True):
        if training_round["status"] in {"training", "validating"} and hospital_id in training_round[
            "selected_hospital_ids"
        ]:
            return training_round
    return None


def _participate(args, token: str) -> dict:
    return participate(
        args.api,
        token,
        args.hospital_id,
        args.round_id,
        args.index,
        args.total,
        args.poison,
        objective_id=args.objective_id,
        csv_path=args.csv_path,
    )


def cmd_participate(args) -> None:
    token = login(args.api, args.email, args.password)
    if not args.round_id:
        training_round = _open_round_for(args.api, token, args.hospital_id)
        if training_round is None:
            print("No open round selected this hospital; nothing to do.")
            return
        args.round_id = training_round["id"]
    print(_participate(args, token))


def cmd_watch(args) -> None:
    token = login(args.api, args.email, args.password)
    handled: set[str] = set()
    print(f"Watching {args.api} for rounds selecting {args.hospital_id} (every {args.poll}s)…")
    while True:
        try:
            training_round = _open_round_for(args.api, token, args.hospital_id)
            if training_round and training_round["id"] not in handled:
                args.round_id = training_round["id"]
                try:
                    print(_participate(args, token))
                except requests.HTTPError as exc:
                    # Already-submitted / closed round → mark handled and move on.
                    print(f"Skipping round {args.round_id}: {exc.response.text if exc.response else exc}")
                handled.add(training_round["id"])
        except requests.RequestException as exc:
            print(f"Poll failed: {exc}")
        time.sleep(args.poll)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MedChain hospital node agent")
    parser.add_argument("command", choices=["participate", "watch"])
    parser.add_argument("--api", default=_cfg("MEDCHAIN_API", "http://127.0.0.1:8000"))
    parser.add_argument("--email", default=_cfg("MEDCHAIN_EMAIL"))
    parser.add_argument("--password", default=_cfg("MEDCHAIN_PASSWORD"))
    parser.add_argument("--hospital-id", default=_cfg("MEDCHAIN_HOSPITAL_ID"))
    parser.add_argument("--objective-id", default=_cfg("MEDCHAIN_OBJECTIVE_ID"))
    parser.add_argument("--csv", dest="csv_path", default=_cfg("MEDCHAIN_CSV_PATH"))
    parser.add_argument("--round-id", default=None)
    parser.add_argument("--index", type=int, default=int(_cfg("MEDCHAIN_NODE_INDEX", "0")))
    parser.add_argument("--total", type=int, default=int(_cfg("MEDCHAIN_NODE_TOTAL", "1")))
    parser.add_argument("--poll", type=int, default=int(_cfg("MEDCHAIN_POLL_SECONDS", "10")))
    parser.add_argument("--poison", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.email = _require(args.email, "MEDCHAIN_EMAIL")
    args.password = _require(args.password, "MEDCHAIN_PASSWORD")
    args.hospital_id = _require(args.hospital_id, "MEDCHAIN_HOSPITAL_ID")
    if args.command == "participate":
        cmd_participate(args)
    else:
        cmd_watch(args)


if __name__ == "__main__":
    main()
