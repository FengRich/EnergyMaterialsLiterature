"""Command line entry points for CI, local preview, and recovery."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .model import ROOT, load_journals
from .site import build
from .sources import SourceError
from .sync import load_decisions, read_state, synchronize, validate_state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=ROOT / "data/state.json")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sync", help="Fetch and persist incremental metadata")
    commands.add_parser("validate", help="Validate papers, reviews, licenses, and reports")
    build_parser = commands.add_parser("build", help="Build the static site and RSS")
    build_parser.add_argument("--output", type=Path, default=ROOT / "dist")
    build_parser.add_argument("--site-url", default="http://127.0.0.1:8000/")
    build_parser.add_argument("--repository")
    build_parser.add_argument("--retrieval-failed", action="store_true",
                              help="Show a retrieval warning on the last validated edition")
    args = parser.parse_args(argv)
    try:
        if args.command == "sync":
            state = synchronize(args.state)
        else:
            journals = load_journals()
            load_decisions(ROOT / "config/reviews.json")
            licenses = load_decisions(ROOT / "config/abstract-licenses.json", licensing=True)
            state = read_state(args.state)
            validate_state(state, journals, licenses)
            if args.command == "build":
                if args.retrieval_failed:
                    stamp = datetime.now(timezone.utc).date().isoformat()
                    state["sources"]["Latest attempt"] = {
                        "state": "failed",
                        "detail": f"Retrieval failed on {stamp} UTC. Showing the last validated data. See Actions.",
                    }
                build(state, args.output, journals, args.site_url, args.repository)
        print(f"{args.command}: {len(state['papers'])} records, {len(state['reports'])} editions")
    except SourceError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
        print(f"{args.command} failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
