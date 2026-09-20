"""Run every test module and report one total.

    python tests\run_all.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODULES = ["test_golden.py", "test_fsops.py"]

failed = False
for mod in MODULES:
    print("=" * 62)
    print(mod)
    print("=" * 62)
    sys.stdout.flush()          # keep the parent's headers with the child's output
    proc = subprocess.run([sys.executable, os.path.join(HERE, mod)])
    if proc.returncode != 0:
        failed = True
    print()

print("ALL SUITES PASSED" if not failed else "THERE WERE FAILURES")
sys.exit(1 if failed else 0)
