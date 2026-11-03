"""The verification stamp toolcheck.json for the content repository (see src/d4loc/toolcheck.py).

  python dev/run.py toolcheck                      write the stamp into content/ (after python dev/run.py voice and public)
  python dev/run.py toolcheck --verify             check that the stamp is valid (exit code 1 if there are problems)
  python dev/run.py toolcheck --verify --content PATH --check-release   the same for another folder, and also compare the application's sum with the release SHA256SUMS
The content repository's CI runs exactly this command."""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from d4loc import toolcheck
from tools import paths

TOOL_REPO = "vladmu/d4loc-ua-tool"


def release_hashes(version):
    url = f"https://github.com/{TOOL_REPO}/releases/download/v{version}/SHA256SUMS.txt"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return {line.split()[0].lower() for line in r.read().decode("utf-8").splitlines() if line.strip()}
    except (urllib.error.URLError, OSError):
        return set()


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--verify", action="store_true")
    p.add_argument("--content", default=paths.CONTENT)
    p.add_argument("--check-release", action="store_true", help="звірити суму застосунку з SHA256SUMS.txt релізу цієї версії")
    cfg = p.parse_args()
    if not cfg.verify:
        data = toolcheck.write(cfg.content)
        print(f"Записано {toolcheck.FILE}: файлів {len(data['files'])}, зауважень {data['checks']['warnings']}, застосунок {data['tool']['version']}")
        return 0
    known = None
    if cfg.check_release:
        try:
            with open(os.path.join(cfg.content, toolcheck.FILE), encoding="utf-8") as f:
                ver = json.load(f)["tool"]["version"]
        except (OSError, ValueError, KeyError):
            ver = None
        known = release_hashes(ver) if ver else set()
    problems = toolcheck.verify(cfg.content, known)
    for pr in problems:
        print("ПРОБЛЕМА:", pr)
    print("Штамп чинний." if not problems else f"Проблем: {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
