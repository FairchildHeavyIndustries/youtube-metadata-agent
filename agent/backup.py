"""Write an immutable backup of current_metadata.json before any changes."""

import argparse
import shutil
from datetime import date
from pathlib import Path


def backup(client_name: str) -> Path:
    output_dir = Path(f"clients/{client_name}/output")
    source = output_dir / "current_metadata.json"

    if not source.exists():
        raise FileNotFoundError(
            f"{source} not found. Run fetch.py first."
        )

    today = date.today().isoformat()
    dest = output_dir / f"original_backup_{today}.json"

    if dest.exists():
        raise FileExistsError(
            f"Backup {dest} already exists for today. "
            "Aborting to protect the original backup."
        )

    shutil.copy2(source, dest)
    print(f"Backup written to {dest}")
    return dest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    args = parser.parse_args()
    backup(args.client)
