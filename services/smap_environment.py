"""Display-only SMAP NRT retrievals; never imported by prediction services.

Quality/depth: https://nsidc.org/sites/default/files/documents/user-guide/spl2smp-v009-userguide.pdf
Flags 0/8 are recommended. At low latitudes the radiometer freeze flag can be
false; the model freeze bit and effective soil temperature determine acceptance.
"""
from __future__ import annotations

import io
import math
import os
import re
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from threading import Lock
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

import h5py
import numpy as np

UNAVAILABLE = "Live data unavailable."
CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
MAX_DISTANCE_KM = 75.0
MAX_AGE_HOURS = 72
MAX_FILE_BYTES = 32 * 1024 * 1024
CACHE_SECONDS = 1800
FIELDS = ("latitude", "longitude", "EASE_row_index", "EASE_column_index",
          "soil_moisture", "retrieval_qual_flag", "surface_flag",
          "surface_temperature", "grid_surface_status", "tb_time_utc")


class SmapUnavailable(Exception):
    def __init__(self):
        super().__init__(UNAVAILABLE)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def _read(url, deadline, token=None, limit=MAX_FILE_BYTES):
    """No implicit redirects, disk cookies, logging, or raw provider exceptions."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SmapUnavailable()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with build_opener(_NoRedirect()).open(Request(url, headers=headers), timeout=min(8, remaining)) as response:
        if response.status != 200:
            raise SmapUnavailable()
        chunks, size = [], 0
        while True:
            if time.monotonic() >= deadline:
                raise SmapUnavailable()
            chunk = response.read(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise SmapUnavailable()
            chunks.append(chunk)
        return b"".join(chunks)


def _download(url, token, deadline):
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname != "data.nsidc.earthdatacloud.nasa.gov"
            or parsed.username or parsed.port not in (None, 443)
            or not parsed.path.startswith("/nsidc-cumulus-prod-protected/SMAP/SPL2SMP_NRT/107/")
            or not parsed.path.endswith(".h5") or parsed.query or parsed.fragment):
        raise SmapUnavailable()
    try:
        return _read(url, deadline, token)
    except HTTPError as error:
        if error.code != 303:
            raise SmapUnavailable() from None
        target = error.headers.get("Location", "")
        delivery = urlparse(target)
        # NASA's signed delivery URL is used only in memory. Never forward the
        # Earthdata bearer token to CloudFront, nor follow further redirects.
        if (delivery.scheme != "https" or not re.fullmatch(r"d[a-z0-9]+\.cloudfront\.net", delivery.hostname or "")
                or delivery.username or delivery.port not in (None, 443)
                or not delivery.path.endswith("/" + parsed.path.rsplit("/", 1)[-1])):
            raise SmapUnavailable() from None
        return _read(target, deadline)


def parse_granule(content):
    if not content.startswith(b"\x89HDF\r\n\x1a\n"):
        raise SmapUnavailable()
    with h5py.File(io.BytesIO(content), "r") as file:
        group = file["Soil_Moisture_Retrieval_Data"]
        arrays = {name: group[name][:] for name in FIELDS}
        shape = arrays["latitude"].shape
        if len(shape) != 1 or not shape[0] or shape[0] > 500000 or any(a.shape != shape for a in arrays.values()):
            raise SmapUnavailable()
        attributes = {name: dict(group[name].attrs) for name in FIELDS}
        unit = group["soil_moisture"].attrs["units"]
        if isinstance(unit, bytes):
            unit = unit.decode()
        if unit not in ("cm**3/cm**3", "m**3/m**3", "m3 m-3"):
            raise SmapUnavailable()
        resolution = float(file["Metadata/GridSpatialRepresentation"].attrs["resolution"])
        if not math.isfinite(resolution) or resolution != 36:
            raise SmapUnavailable()
        return arrays, attributes, unit, resolution


def select_observation(parsed, latitude, longitude, granule, now):
    arrays, attrs, unit, resolution = parsed
    sm = arrays["soil_moisture"]
    minimum, maximum = float(attrs["soil_moisture"]["valid_min"]), float(attrs["soil_moisture"]["valid_max"])
    # Enforce the documented product range as well as the file attributes.
    if not (0.019 <= minimum <= 0.021 and maximum == 0.5):
        raise SmapUnavailable()
    lat, lon = arrays["latitude"], arrays["longitude"]
    sf, qf = arrays["surface_flag"], arrays["retrieval_qual_flag"]
    temp = arrays["surface_temperature"]
    mask = (np.isfinite(sm) & (sm != -9999) & (sm != attrs["soil_moisture"]["_FillValue"])
            & (sm >= minimum) & (sm <= maximum) & np.isin(qf, [0, 8])
            & np.isfinite(lat) & np.isfinite(lon) & (np.abs(lat) <= 85.044) & (np.abs(lon) <= 180)
            & (arrays["grid_surface_status"] == 0)
            & ((sf == 0) | ((sf == 128) & (np.abs(lat) < 45)))
            & np.isfinite(temp) & (temp > 273.15) & (temp <= 350)
            & (temp != attrs["surface_temperature"]["_FillValue"])
            & (arrays["EASE_row_index"] >= 0) & (arrays["EASE_row_index"] <= 405)
            & (arrays["EASE_column_index"] >= 0) & (arrays["EASE_column_index"] <= 963))
    radians = np.pi / 180
    hav = (np.sin((lat - latitude) * radians / 2) ** 2
           + math.cos(latitude * radians) * np.cos(lat * radians) * np.sin((lon - longitude) * radians / 2) ** 2)
    distances = 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(hav, 0, 1)))
    indices = np.flatnonzero(mask & (distances <= MAX_DISTANCE_KM))
    for index in sorted(indices, key=lambda i: distances[i]):
        raw = arrays["tb_time_utc"][index]
        try:
            observed = datetime.fromisoformat((raw.decode() if isinstance(raw, bytes) else str(raw)).replace("Z", "+00:00"))
            if observed.tzinfo is None or not now - timedelta(hours=MAX_AGE_HOURS) <= observed <= now + timedelta(minutes=5):
                continue
        except (ValueError, UnicodeError):
            continue
        value = float(sm[index])
        return {"source": "NASA SMAP NRT", "soil_moisture_percent": value * 100,
                "native_value": value, "native_unit": unit, "unit": "% water by volume",
                "observed_at": observed.astimezone(timezone.utc).isoformat(),
                "spatial_resolution_km": resolution, "depth_cm": [0, 5], "granule": granule,
                "grid": {"row": int(arrays["EASE_row_index"][index]), "column": int(arrays["EASE_column_index"][index]),
                         "latitude": float(lat[index]), "longitude": float(lon[index])},
                "distance_km": float(distances[index]), "retrieval_qual_flag": int(qf[index]),
                "surface_flag": int(sf[index]), "surface_temperature_kelvin": float(temp[index])}
    return None


class SmapService:
    """Bounded process-local caches and single-flight ingestion; no database writes."""
    def __init__(self):
        self._lock = Lock()
        self._catalog = OrderedDict()
        self._granules = OrderedDict()

    @staticmethod
    def _put(cache, key, value, ttl, size):
        cache[key] = (time.monotonic() + ttl, value)
        cache.move_to_end(key)
        while len(cache) > size:
            cache.popitem(last=False)

    @staticmethod
    def _get(cache, key):
        item = cache.get(key)
        if item and item[0] > time.monotonic():
            cache.move_to_end(key)
            return True, item[1]
        cache.pop(key, None)
        return False, None

    def fetch(self, latitude, longitude):
        if (isinstance(latitude, bool) or isinstance(longitude, bool)
                or not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float))
                or not math.isfinite(latitude) or not math.isfinite(longitude)
                or abs(latitude) > 90 or abs(longitude) > 180):
            raise SmapUnavailable()
        token = os.getenv("EARTHDATA_TOKEN", "").strip()
        if not token or abs(latitude) > 85.044:
            raise SmapUnavailable()
        if not self._lock.acquire(timeout=30):
            raise SmapUnavailable()
        key = (round(latitude * 4) / 4, round(longitude * 4) / 4)
        try:
            now = datetime.now(timezone.utc)
            deadline = time.monotonic() + 30
            hit, entries = self._get(self._catalog, key)
            if not hit:
                import json
                query = urlencode({"short_name": "SPL2SMP_NRT", "version": "107",
                                   "circle": f"{key[1]},{key[0]},100000", "sort_key": "-start_date", "page_size": 8,
                                   "temporal": f"{(now - timedelta(hours=MAX_AGE_HOURS)).isoformat()},{now.isoformat()}"})
                entries = json.loads(_read(CMR_URL + "?" + query, deadline, limit=2 * 1024 * 1024))["feed"]["entry"]
                entries = sorted(entries, key=lambda entry: (entry["time_start"], entry["title"]), reverse=True)
                self._put(self._catalog, key, entries, CACHE_SECONDS, 128)
            # Prefer the latest overpass, then its nearest quality-valid cell.
            for entry in entries[:4]:
                url = next((link["href"] for link in entry["links"] if link.get("rel", "").endswith("/data#")
                            and link.get("href", "").endswith(".h5")), None)
                if not url:
                    continue
                name = urlparse(url).path.rsplit("/", 1)[-1]
                if not re.fullmatch(r"SMAP_L2_SM_P_NRT_[A-Za-z0-9_]+\.h5", name):
                    raise SmapUnavailable()
                hit, parsed = self._get(self._granules, name)
                if not hit:
                    parsed = parse_granule(_download(url, token, deadline))
                    self._put(self._granules, name, parsed, CACHE_SECONDS, 8)
                observation = select_observation(parsed, latitude, longitude, name, now)
                if observation:
                    return observation
            raise SmapUnavailable()
        except Exception:
            # Failures are briefly cached to avoid repeated upstream request storms.
            self._put(self._catalog, key, [], 300, 128)
            raise SmapUnavailable() from None
        finally:
            self._lock.release()


smap_service = SmapService()
