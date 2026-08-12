import shutil
import subprocess
from pathlib import Path
import sys

def main() -> None:
    subprocess.run(["ignis", "quit"], check=False)

    config_dir = Path.home() / ".config" / "ignis"
    exosting = Path(__file__).resolve().parent.parent

    if config_dir.exists():
        shutil.rmtree(config_dir)

    shutil.copytree(exosting, config_dir)

    subprocess.run(
        ["ignis", "init"],
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        check=True,
)


if __name__ == "__main__":
    main()