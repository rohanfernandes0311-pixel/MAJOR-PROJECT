"""Download the manifest-listed SRTM tiles and verify every SHA-256 checksum."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/research/south_india_environmental_features/terrain_manifest.json"
DEFAULT_OUTPUT = ROOT / "data/research/south_india_environmental_features/sources/srtm_v3"
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def download_tile(tile: str, expected: str, url_template: str, output_dir: Path) -> str:
    if Path(tile).name != tile or not tile.endswith(".hgt.gz"):
        raise ValueError(f"Invalid tile name in manifest: {tile!r}")
    if not SHA256_PATTERN.fullmatch(expected):
        raise ValueError(f"Invalid SHA-256 checksum in manifest for {tile}")

    destination = output_dir / tile
    if destination.is_file() and sha256_file(destination) == expected.upper():
        return "verified-existing"

    url = url_template.format(lat_band=tile[:3], tile=tile)
    if urlparse(url).scheme != "https":
        raise ValueError("Terrain tile URLs must use HTTPS")

    temporary_path: Path | None = None
    digest = hashlib.sha256()
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{tile}.", suffix=".part", dir=output_dir, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            with requests.get(url, stream=True, timeout=(10, 90)) as response:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        temporary.write(chunk)
                        digest.update(chunk)

        if digest.hexdigest().upper() != expected.upper():
            raise ValueError(f"SHA-256 mismatch for {tile}; downloaded file was discarded")

        temporary_path.replace(destination)
        return "downloaded-and-verified"
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    dem = manifest["dem"]
    url_template = dem["url_template"]
    checksums = dem["tile_checksums"]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for tile, expected in sorted(checksums.items()):
        result = download_tile(tile, expected, url_template, args.output_dir)
        print(f"{result}: {tile}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
