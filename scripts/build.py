#!/usr/bin/env python3
"""Build the static site and a machine-readable catalog from the original assets."""
import csv
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from urllib.parse import quote

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
DIST = ROOT / "dist"
SRC = ROOT / "src"

DESCRIPTIONS = {
    "runspindle_bloomberg_product.pdf": ("Product concept", "16-page presentation introducing two workflow modes, operator review, integration roles and the 40-case catalog.", ["runspindle_bloomberg_workflows.csv", "runspindle_bloomberg_ranked.csv"]),
    "runspindle_bloomberg_workflows.csv": ("Workflow source data", "Canonical 40-case catalog: eight cross-system business scenarios and 32 Terminal-only paper scenarios, with methods, checks, verification, assumptions and source URLs.", ["runspindle_bloomberg_ranked.csv", "runspindle_bloomberg_product.pdf"]),
    "runspindle_bloomberg_ranked.csv": ("Ranking data", "The same 40 cases with supplied priority scores and ranking rationale; scenario-level judgment, not measured return or product acceptance.", ["runspindle_bloomberg_workflows.csv"]),
    "runspindle-paper.pdf": ("Research paper", "12-page research and design proposal, Testing Maintained Workflows Under Explicit Authority; sets the evidence and evaluation boundary.", ["runspindle-paper-exact-v5.zip", "Runspindle-UI-gallery.pdf"]),
    "runspindle-paper-exact-v5.zip": ("Paper package", "Archive containing the research paper and a manifest with its exact SHA-256 and byte count.", ["runspindle-paper.pdf"]),
    "Runspindle-UI-gallery.pdf": ("Original UI gallery", "29-page raster-only conceptual interface gallery; source UI panels for the revised presentation.", ["Runspindle_Revised_Gallery.pdf", "Runspindle-UI-illustrations.zip"]),
    "Runspindle-UI-illustrations.zip": ("UI illustrations", "29 named conceptual illustration PNGs plus INDEX.txt, corresponding to the original gallery sequence.", ["Runspindle-UI-gallery.pdf", "Runspindle_Gallery_Index.html"]),
    "Runspindle_Revised_Gallery.pdf": ("Revised gallery", "37-page Pet Tabletop gallery: 29 original-slide compositions and eight new synthetic business cases.", ["Runspindle_Gallery_Index.html", "Runspindle_Gallery_37_PNGs.zip"]),
    "Runspindle_Gallery_Index.html": ("Gallery source index", "Page-by-page map, evidence boundary and official Bloomberg citations for the eight added cases.", ["Runspindle_Revised_Gallery.pdf", "Runspindle_Gallery_37_PNGs.zip"]),
    "Runspindle_Gallery_37_PNGs.zip": ("Gallery page images", "37 full-size PNGs matching the revised gallery, pages 01–37.", ["Runspindle_Revised_Gallery.pdf", "Runspindle_Gallery_Index.html"]),
    "Runspindle_Gallery_37_PNGs (1).zip": ("Duplicate gallery archive", "Byte-identical duplicate of Runspindle_Gallery_37_PNGs.zip, retained as supplied.", ["Runspindle_Gallery_37_PNGs.zip"]),
}

def read_csv(name):
    with (ASSETS / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(SRC, DIST)
    shutil.copytree(ASSETS, DIST / "assets")
    (DIST / ".nojekyll").touch()

    records = []
    for path in sorted(ASSETS.iterdir()):
        if not path.is_file() or path.name not in DESCRIPTIONS:
            continue
        kind, description, related = DESCRIPTIONS[path.name]
        records.append({"name": path.name, "kind": kind, "description": description,
                        "bytes": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "url": "assets/" + quote(path.name),
                        "related": related})
    (DIST / "asset-catalog.json").write_text(json.dumps(records, ensure_ascii=False, indent=2))

    ranked = read_csv("runspindle_bloomberg_ranked.csv")
    workflows = read_csv("runspindle_bloomberg_workflows.csv")
    by_id = {row["example_id"]: row for row in workflows}
    cases = []
    for row in ranked:
        case = dict(by_id[row["example_id"]])
        case.update({"rank": int(row["priority_rank"]), "score": float(row["priority_score"]),
                     "rationale": row["ranking_rationale"], "scope_of_claim": row["scope_of_claim"]})
        cases.append(case)
    assert len(cases) == len(by_id) == 40
    (DIST / "workflows.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2))

    gallery_dir = DIST / "gallery"
    gallery_dir.mkdir()
    with zipfile.ZipFile(ASSETS / "Runspindle_Gallery_37_PNGs.zip") as z:
        names = sorted(n for n in z.namelist() if n.lower().endswith(".png"))
        assert len(names) == 37
        for i, name in enumerate(names, 1):
            with z.open(name) as source:
                with Image.open(source) as im:
                    im.thumbnail((1120, 630), Image.Resampling.LANCZOS)
                    im.convert("RGB").save(gallery_dir / f"{i:02}.webp", "WEBP", quality=82, method=6)
    print(f"Built {len(cases)} workflows, {len(records)} assets, {len(names)} gallery previews in {DIST}")

if __name__ == "__main__":
    main()
