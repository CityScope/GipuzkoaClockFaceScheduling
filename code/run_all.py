"""Run every region in parallel (analysis + map, overview picture, services audit).
Usage: python3 code/run_all.py [region ...]   (default: all regions in code/regions/)"""
import subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CODE = Path(__file__).parent
REGIONS = sys.argv[1:] or sorted(p.stem for p in (CODE / "regions").glob("*.py") if not p.stem.startswith("_"))


def run(region):
    t = time.time()
    steps = [["run_analysis.py", region], ["make_overview.py", region], ["audit_services.py", region]]
    log = []
    for s in steps:
        r = subprocess.run([sys.executable, "-W", "ignore", str(CODE / s[0]), *s[1:]], capture_output=True, text=True)
        log.append(r.stdout[-400:] if r.returncode == 0 else r.stderr[-1500:])
        if r.returncode:
            return region, time.time() - t, "FAILED in " + s[0] + "\n" + log[-1]
    miss = [l for l in log[-1].splitlines() if "missing:" in l]
    return region, time.time() - t, miss[0] if miss else "ok"


if __name__ == "__main__":
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=min(3, len(REGIONS))) as ex:        # 3 at a time: memory of the national feeds
        for region, dt, msg in ex.map(run, REGIONS):
            print(f"{region:16s} {dt:6.1f} s  {msg}")
    print(f"all done in {time.time() - t0:.1f} s")
