#!/usr/bin/env python3
"""Create the site's full-character WOFF2 fonts from the RinMincho 1.0.0 ZIP."""

import argparse
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from fontTools.ttLib import TTFont


FAMILY = "Prismawelt Mincho"
ARCHIVE_ROOT = "RinMincho_v1.0.0"
DESTINATION = Path(__file__).resolve().parents[1] / "assets/fonts/prismawelt-mincho"


def build_font(archive, style, compressor, temporary):
    source = archive.read(f"{ARCHIVE_ROOT}/RinMincho-{style}.ttf")
    with TTFont(BytesIO(source), recalcTimestamp=False) as font:
        glyph_count = len(font.getGlyphOrder())
        character_count = len(font.getBestCmap())
        names = {
            1: FAMILY,
            2: style,
            3: f"PrismaweltMincho-1.000-{style}",
            4: f"{FAMILY} {style}",
            6: f"PrismaweltMincho-{style}",
            16: FAMILY,
            17: style,
            18: f"{FAMILY} {style}",
            21: FAMILY,
            22: style,
        }
        for record in list(font["name"].names):
            if record.nameID in names:
                font["name"].setName(
                    names[record.nameID],
                    record.nameID,
                    record.platformID,
                    record.platEncID,
                    record.langID,
                )
        for name_id, value in names.items():
            font["name"].setName(value, name_id, 3, 1, 0x409)
        renamed = temporary / f"PrismaweltMincho-{style}.ttf"
        font.save(renamed)

    subprocess.run([compressor, str(renamed)], check=True, capture_output=True)
    output = DESTINATION / f"PrismaweltMincho-{style}.woff2"
    shutil.copyfile(renamed.with_suffix(".woff2"), output)
    print(
        f"{output.name}: {glyph_count} glyphs, {character_count} characters, "
        f"{output.stat().st_size:,} bytes"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="RinMincho_v1.0.0.zip")
    args = parser.parse_args()
    compressor = shutil.which("woff2_compress")
    if not compressor:
        parser.error("woff2_compress is required (install the woff2 package)")

    DESTINATION.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.archive) as archive, TemporaryDirectory(
        prefix="prismawelt-mincho-"
    ) as temporary:
        for style in ("Regular", "Bold"):
            build_font(archive, style, compressor, Path(temporary))
        license_text = archive.read(f"{ARCHIVE_ROOT}/OFL.txt")
        (DESTINATION / "OFL.txt").write_bytes(license_text.replace(b"\r\n", b"\n"))


if __name__ == "__main__":
    main()
