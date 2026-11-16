"""Download one authorized Copernicus product for the Kodagu research pilot.

Credentials are read from CDSE_USERNAME/CDSE_PASSWORD or
CDSE_CLIENT_ID/CDSE_CLIENT_SECRET, or from an ignored JSON credentials file.
Secret values are never printed or written to research artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


PRODUCT_ID = (
    "S1B_IW_GRDH_1SDV_20180815T130642_20180815T130711_012274_0169DC_C6B4_COG"
)
PRODUCT_UUID = "1679bab8-605a-493e-9ca2-396a4b9349e7"
SCENE_KEY = "copernicus_s1_20180815_130642_iw_grdh"
TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/"
    "protocol/openid-connect/token"
)
PRODUCT_URL = (
    "https://download.dataspace.copernicus.eu/odata/v1/Products"
    f"({PRODUCT_UUID})/$value"
)
DEFAULT_CREDENTIALS_FILE = Path("config/copernicus_credentials.json")


class DownloadError(RuntimeError):
    """A safe, user-actionable download failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_credentials(path: Path | None) -> dict[str, str]:
    names = ("CDSE_USERNAME", "CDSE_PASSWORD", "CDSE_CLIENT_ID", "CDSE_CLIENT_SECRET")
    values = {name: os.environ.get(name, "").strip() for name in names}
    password_env_present = bool(values["CDSE_USERNAME"] or values["CDSE_PASSWORD"])
    client_env_present = bool(values["CDSE_CLIENT_ID"] or values["CDSE_CLIENT_SECRET"])
    if values["CDSE_USERNAME"] and values["CDSE_PASSWORD"]:
        return {
            "grant_type": "password",
            "username": values["CDSE_USERNAME"],
            "password": values["CDSE_PASSWORD"],
            "client_id": values["CDSE_CLIENT_ID"] or "cdse-public",
        }
    if values["CDSE_CLIENT_ID"] and values["CDSE_CLIENT_SECRET"]:
        return {
            "grant_type": "client_credentials",
            "client_id": values["CDSE_CLIENT_ID"],
            "client_secret": values["CDSE_CLIENT_SECRET"],
        }
    if password_env_present or client_env_present:
        raise DownloadError(
            "Copernicus environment credentials are incomplete. Set both "
            "CDSE_USERNAME and CDSE_PASSWORD, or both CDSE_CLIENT_ID and "
            "CDSE_CLIENT_SECRET. No download request was made."
        )

    credentials_path = path or DEFAULT_CREDENTIALS_FILE
    if not credentials_path.is_absolute():
        credentials_path = Path.cwd() / credentials_path
    if not credentials_path.is_file():
        raise DownloadError(
            "Copernicus credentials are unavailable. Set CDSE_USERNAME and "
            "CDSE_PASSWORD, or CDSE_CLIENT_ID and CDSE_CLIENT_SECRET, or create "
            f"the ignored local file {credentials_path}."
        )
    if credentials_path.stat().st_size == 0:
        raise DownloadError(
            f"The Copernicus credentials file is empty: {credentials_path}. "
            "Fill its supported fields locally; no download request was made."
        )
    try:
        contents = credentials_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DownloadError(
            f"Could not read the local Copernicus credentials file: {credentials_path}"
        ) from exc
    try:
        data = json.loads(contents)
    except json.JSONDecodeError as exc:
        raise DownloadError(
            f"The local Copernicus credentials file is not valid JSON: {credentials_path}"
        ) from exc
    if not isinstance(data, dict):
        raise DownloadError(
            f"The Copernicus credentials file must contain a JSON object: {credentials_path}"
        )
    username = data.get("username") or data.get("CDSE_USERNAME")
    password = data.get("password") or data.get("CDSE_PASSWORD")
    client_id = data.get("client_id") or data.get("CDSE_CLIENT_ID")
    client_secret = data.get("client_secret") or data.get("CDSE_CLIENT_SECRET")
    if isinstance(username, str) and isinstance(password, str) and username and password:
        return {
            "grant_type": "password",
            "username": username,
            "password": password,
            "client_id": client_id if isinstance(client_id, str) and client_id else "cdse-public",
        }
    if (
        isinstance(client_id, str)
        and isinstance(client_secret, str)
        and client_id
        and client_secret
    ):
        return {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    raise DownloadError(
        "The local Copernicus credentials file has empty or unsupported credential "
        "fields. Use username/password, or client_id/client_secret; no download "
        "request was made."
    )


def request_token(credentials: dict[str, str], session: requests.Session) -> str:
    try:
        response = session.post(
            TOKEN_URL,
            data=credentials,
            headers={"Accept": "application/json"},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise DownloadError("Copernicus authentication request failed.") from exc
    if response.status_code != 200:
        raise DownloadError(
            "Copernicus authentication was rejected "
            f"(HTTP {response.status_code}); check the local account/client setup."
        )
    try:
        token = response.json().get("access_token")
    except ValueError as exc:
        raise DownloadError("Copernicus authentication returned a non-JSON response.") from exc
    if not isinstance(token, str) or not token:
        raise DownloadError("Copernicus authentication returned no bearer token.")
    return token


def pilot_intersects_scene(register: dict[str, Any]) -> bool:
    pilot = register["pilot"]
    for scene in register["scenes"]:
        if scene.get("local_scene_key") == SCENE_KEY:
            bbox = scene["geometry"]["bbox"]
            return not (
                bbox[2] < pilot["west"]
                or bbox[0] > pilot["east"]
                or bbox[3] < pilot["south"]
                or bbox[1] > pilot["north"]
            )
    raise DownloadError(f"Selected scene {SCENE_KEY} is missing from the scene register.")


def validate_product_archive(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        prefix = stream.read(512)
    if prefix.startswith(b"<") or prefix.startswith(b"{") or b"<html" in prefix.lower():
        raise DownloadError("The downloaded response appears to be HTML or JSON, not a product.")
    if not zipfile.is_zipfile(path):
        raise DownloadError("The downloaded response is not a valid ZIP scientific product archive.")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    lower_names = [name.lower() for name in names]
    has_safe = any(".safe/" in name or name.endswith(".safe") for name in lower_names)
    has_measurement = any("/measurement/" in name for name in lower_names)
    has_raster = any(name.endswith((".tif", ".tiff")) for name in lower_names)
    if not (has_safe and has_measurement and has_raster):
        raise DownloadError(
            "The ZIP lacks the expected Sentinel-1 SAFE measurement raster structure."
        )
    return {
        "file_format": "ZIP",
        "archive_entries": len(names),
        "contains_safe_structure": has_safe,
        "contains_measurement_directory": has_measurement,
        "contains_raster": has_raster,
    }


def download_product(
    session: requests.Session,
    token: str,
    destination: Path,
    resume_partial: bool = False,
) -> tuple[int, str, dict[str, Any]]:
    part = destination.with_name(destination.name + ".part")
    if destination.exists():
        try:
            validation = validate_product_archive(destination)
        except DownloadError as exc:
            raise DownloadError(
                f"Refusing to overwrite existing invalid file: {destination}. {exc}"
            ) from exc
        digest = hashlib.sha256(destination.read_bytes()).hexdigest().upper()
        return destination.stat().st_size, digest, validation
    if part.exists():
        if not resume_partial:
            raise DownloadError(
                f"A partial file already exists at {part}. It was not overwritten. "
                "Re-run with --resume-partial only if resumption is explicitly desired."
            )
        existing_size = part.stat().st_size
        range_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/zip",
            "Range": f"bytes={existing_size}-",
        }
    else:
        existing_size = 0
        range_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/zip",
        }
    part.parent.mkdir(parents=True, exist_ok=True)
    try:
        with session.get(
            PRODUCT_URL,
            headers=range_headers,
            stream=True,
            timeout=(30, 120),
        ) as response:
            if response.status_code in (401, 403):
                raise DownloadError(
                    "Copernicus product download was rejected by authorization "
                    f"(HTTP {response.status_code})."
                )
            expected_status = 206 if existing_size else 200
            if response.status_code != expected_status:
                if existing_size:
                    raise DownloadError(
                        "The Copernicus endpoint did not confirm safe range resumption "
                        f"(HTTP {response.status_code}); the partial file was retained."
                    )
                raise DownloadError(
                    f"Copernicus product download failed with HTTP {response.status_code}."
                )
            content_type = response.headers.get("Content-Type", "").lower()
            if "html" in content_type or "json" in content_type:
                raise DownloadError("Copernicus returned an HTML/JSON response, not a product.")
            if existing_size:
                content_range = response.headers.get("Content-Range", "")
                if not content_range.startswith(f"bytes {existing_size}-"):
                    raise DownloadError(
                        "The Copernicus response had no matching Content-Range; "
                        "the partial file was retained."
                    )
                mode = "ab"
            else:
                mode = "xb"
            with part.open(mode) as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output.write(chunk)
        validation = validate_product_archive(part)
        digest = hashlib.sha256(part.read_bytes()).hexdigest().upper()
        part.replace(destination)
        return destination.stat().st_size, digest, validation
    except (requests.RequestException, OSError) as exc:
        raise DownloadError(
            "The product download did not complete; any partial file was retained for inspection."
        ) from exc
    except DownloadError:
        if part.exists():
            part.rename(part.with_name(part.name + ".invalid"))
        raise


def update_artifacts(
    repo: Path,
    register: dict[str, Any],
    manifest: dict[str, Any],
    destination: Path,
    size: int,
    digest: str,
    validation: dict[str, Any],
) -> None:
    retrieved = utc_now()
    relative = destination.relative_to(repo).as_posix()
    entry = {
        "local_file": relative,
        "local_scene_key": SCENE_KEY,
        "product_id": PRODUCT_ID,
        "asset_type": "full_scientific_product",
        "source_url": PRODUCT_URL,
        "retrieved_at_utc": retrieved,
        "bytes": size,
        "sha256": digest,
        "validation_status": "validated_sentinel_1_grd_archive",
        "coverage_status": "catalog_footprint_intersects_pilot",
        "quality_screening": {
            **validation,
            "polarization": "VV/VH",
            "instrument_mode": "IW",
            "pixel_level_pilot_quality": "pending_human_review",
            "reviewable_for_non_event": False,
        },
        "license_access_notes": "Downloaded through the authenticated Copernicus Data Space OData endpoint.",
    }
    manifest["files"] = [
        existing
        for existing in manifest.get("files", [])
        if existing.get("product_id") != PRODUCT_ID
        or existing.get("asset_type") != "full_scientific_product"
    ]
    manifest["files"].append(entry)
    manifest["integrity_statement"] = (
        "One validated Sentinel-1 GRD scientific product is retained with a checksum. "
        "The existing browse asset remains separate. Human review is pending; no labels "
        "were created."
    )
    for scene in register["scenes"]:
        if scene.get("local_scene_key") == SCENE_KEY:
            scene["access"]["imagery_bytes_downloaded"] = True
            scene["access"]["full_product_path"] = relative
            scene["access"]["full_product_sha256"] = digest
            scene["validation_status"] = "full_product_downloaded_human_review_pending"
            scene["missing_fields"] = [
                "pilot_level_quality_metrics",
                "pre_event_pair",
                "reviewer_assessment",
            ]
            break
    register["summary"]["imagery_downloaded"] = True
    register["summary"]["downloaded_full_products"] = 1
    register["summary"]["human_review_completed"] = False

    manifest_path = repo / "data/research/kodagu_imagery_download_manifest.json"
    register_path = repo / "data/research/kodagu_imagery_scene_register.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    register_path.write_text(json.dumps(register, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument(
        "--resume-partial",
        action="store_true",
        help="Resume an existing .part file only when the endpoint returns a matching 206 response.",
    )
    args = parser.parse_args()
    repo = args.repo.resolve()
    register_path = repo / "data/research/kodagu_imagery_scene_register.json"
    manifest_path = repo / "data/research/kodagu_imagery_download_manifest.json"
    destination = repo / "data/research/kodagu_imagery_downloads" / f"{PRODUCT_ID}.zip"
    try:
        register = json.loads(register_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not pilot_intersects_scene(register):
            raise DownloadError("Selected product footprint does not intersect the Kodagu pilot.")
        credentials = load_credentials(args.credentials_file)
        session = requests.Session()
        token = request_token(credentials, session)
        size, digest, validation = download_product(
            session, token, destination, resume_partial=args.resume_partial
        )
        update_artifacts(repo, register, manifest, destination, size, digest, validation)
        print(f"Validated Copernicus product: {destination}")
        print(f"Bytes: {size}; SHA-256: {digest}")
        return 0
    except (DownloadError, OSError, json.JSONDecodeError) as exc:
        print(f"Download not completed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
