"""Regenerate only the HTML map of a region from the cached analysis (output/<region>/results.pkl).
Use after changing code/make_map.py (layout, popups, legend). Run: python3 code/rebuild_map.py <region>"""
import os, pickle, sys
os.environ["REGION"] = sys.argv[1]
sys.path.insert(0, os.path.dirname(__file__))
from pathlib import Path
from make_map import make_map

out = Path(__file__).parent.parent / "output" / sys.argv[1]
page = out.parent.parent / "maps" / sys.argv[1] / "index.html"   # one URL per region: <site>/maps/<region>/
page.parent.mkdir(parents=True, exist_ok=True)
make_map(pickle.load(open(out / "results.pkl", "rb")), page)
print("rebuilt", page)
