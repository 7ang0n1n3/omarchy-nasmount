#!/usr/bin/env python3
"""Run repository checks without installing the plugin or touching NAS mounts."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(command, env=None):
    print("+ " + " ".join(map(str, command)), flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-qml", action="store_true", help="fail if the Qt 6 test runner is unavailable")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "manifest.json").read_text())
    if manifest.get("schemaVersion") != 1:
        raise ValueError("Expected manifest schema version 1")
    for name in manifest["entryPoints"].values():
        path = ROOT / name
        if not path.is_file() or not path.resolve().is_relative_to(ROOT):
            raise ValueError("Missing or unsafe entry point: " + name)
    for catalog in (ROOT / "i18n").glob("*.json"):
        json.loads(catalog.read_text())
    run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"])
    run(["bash", "-n", "machine/omarchy-nasctl", "machine/90-omarchy-nas"])
    # Prefer known Qt 6 locations; QMLTESTRUNNER can select another Qt 6 runner.
    candidates = [os.environ.get("QMLTESTRUNNER"), "/usr/lib/qt6/bin/qmltestrunner", shutil.which("qmltestrunner6"), shutil.which("qmltestrunner")]
    runner = next((p for p in candidates if p and os.path.isfile(p) and os.access(p, os.X_OK)), None)
    if runner:
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")
        run([runner, "-input", "tests/qml", "-import", "tests/qml/imports", "-o", "-,txt"], env)
    elif args.require_qml:
        raise RuntimeError("Qt 6 qmltestrunner is required; set QMLTESTRUNNER to its path")
    else:
        print("SKIP: QML tests (Qt 6 qmltestrunner not found)")
    if shutil.which("omarchy"):
        run(["omarchy", "plugin", "validate", "."])
    else:
        print("SKIP: Omarchy host validation (omarchy not found)")
    print("Available checks passed. See VALIDATION.md for separate live checks.")


if __name__ == "__main__":
    main()
