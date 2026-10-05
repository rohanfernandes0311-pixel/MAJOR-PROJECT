"""Display-only IMERG Early V07 rates. Never supplies prediction features.

Product definition: https://gpm.nasa.gov/sites/default/files/2024-06/filespec.GPM_.pdf
Section 5.59: precipitation 0..200 mm/hr; quality index 0..1, higher is better.
There is no categorical recommended-retrieval mask for this merged product.
We reject missing quality and the lowest index (0); this is a conservative
display policy, not a NASA-defined quality threshold. No neighbouring pixels,
interpolation, accumulation conversion, or alternate rainfall provider is used.
"""
from __future__ import annotations

import io
import math
import os
import re
import time
from datetime import datetime, timedelta, timezone
from threading import Lock
from urllib.parse import urlparse

import h5py
import numpy as np
import requests

UNAVAILABLE = "Live data unavailable."
SOURCE = "NASA GPM IMERG Early"
CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
MAX_AGE_HOURS = 12  # Explicit recent-data policy, including nominal Early latency.
CATALOG_SECONDS = 600
FAILURE_SECONDS = 300
MAX_FILE_BYTES = 64 * 1024 * 1024
NAME = re.compile(r"3B-HHR-E\.MS\.MRG\.3IMERG\.(\d{8})-S(\d{6})-E(\d{6})\.\d{4}\.V07[A-Z]\.HDF5")


class ImergUnavailable(Exception):
    def __init__(self):
        super().__init__(UNAVAILABLE)


def _text(value):
    if isinstance(value, np.ndarray):
        if value.size != 1:
            raise ImergUnavailable()
        value = value.item()
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ImergUnavailable()
    return result.astimezone(timezone.utc)


def _read(url, deadline, token=None, limit=MAX_FILE_BYTES):
    """Bounded streaming, no implicit redirects, cookies, or provider logging."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ImergUnavailable()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with requests.get(url, headers=headers, timeout=(min(8, remaining), min(8, remaining)),
                      allow_redirects=False, stream=True) as response:
        if response.status_code in (302, 303) and token:
            target = response.headers.get("Location", "")
            parsed = urlparse(target)
            # NASA's signed delivery URL stays in memory; never forward token.
            if (parsed.scheme == "https" and re.fullmatch(r"d[a-z0-9]+\.cloudfront\.net", parsed.hostname or "")
                    and not parsed.username and parsed.port in (None, 443)
                    and parsed.path.rsplit("/", 1)[-1] == urlparse(url).path.rsplit("/", 1)[-1]):
                return _read(target, deadline, limit=limit)
            raise ImergUnavailable()
        if response.status_code != 200:
            raise ImergUnavailable()
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > limit or time.monotonic() >= deadline:
                raise ImergUnavailable()
            chunks.append(chunk)
        return b"".join(chunks)


def _download(url, token, deadline):
    p = urlparse(url)
    if (p.scheme != "https" or p.hostname != "data.gesdisc.earthdata.nasa.gov"
            or p.username or p.port not in (None, 443) or p.query or p.fragment
            or not p.path.startswith("/data/GPM_L3/GPM_3IMERGHHE.07/")
            or not NAME.fullmatch(p.path.rsplit("/", 1)[-1])):
        raise ImergUnavailable()
    return _read(url, deadline, token)


def parse_granule(content):
    if not content.startswith(b"\x89HDF\r\n\x1a\n"):
        raise ImergUnavailable()
    with h5py.File(io.BytesIO(content), "r") as file:
        header = dict(re.findall(r"(\w+)\s*=\s*([^;]+);", _text(file.attrs["FileHeader"])))
        if header.get("EmptyGranule", "").strip().upper() != "NOT_EMPTY":
            raise ImergUnavailable()
        start = _timestamp(header["StartGranuleDateTime"].strip())
        end = _timestamp(header["StopGranuleDateTime"].strip())
        if not 1799 <= (end-start).total_seconds() <= 1800:
            raise ImergUnavailable()
        group = file["Grid"]
        axes = {}
        for name, bound, maximum in [("lat", 90, 1800), ("lon", 180, 3600)]:
            d = group[name]
            if len(d.shape) != 1 or not 2 <= d.size <= maximum:
                raise ImergUnavailable()
            values = d[:]
            if (not np.isfinite(values).all() or np.any(np.abs(values) > bound)
                    or not np.allclose(np.diff(values), 0.1, atol=2e-5)):
                raise ImergUnavailable()
            axes[name] = values
        fields = {}
        for name in ["precipitation", "precipitationQualityIndex", "randomError"]:
            d = group[name]
            # V07 C/HDF5 order is time, longitude, latitude (spec section 5.59).
            if d.shape != (1, len(axes["lon"]), len(axes["lat"])):
                raise ImergUnavailable()
            if name != "precipitationQualityIndex" and _text(d.attrs["units"]).strip() not in ("mm/hr", "mm/h", "mm/hour"):
                raise ImergUnavailable()
            # Only already physical, unscaled rates are accepted.
            if float(d.attrs.get("scale_factor", 1)) != 1 or float(d.attrs.get("add_offset", 0)) != 0:
                raise ImergUnavailable()
            fields[name] = (d[0], float(d.attrs.get("_FillValue", -9999.9)))
        return {**axes, **fields, "start": start, "end": end}


def select_observation(grid, latitude, longitude, granule, now):
    start, end = grid["start"], grid["end"]
    if start > now + timedelta(minutes=5) or now-start > timedelta(hours=MAX_AGE_HOURS):
        raise ImergUnavailable()
    row = int(np.argmin(abs(grid["lat"]-latitude)))
    column = int(np.argmin(abs(grid["lon"]-longitude)))
    lat, lon = float(grid["lat"][row]), float(grid["lon"][column])
    if abs(lat-latitude) > 0.05002 or abs(lon-longitude) > 0.05002:
        raise ImergUnavailable()
    values = {}
    for name, maximum in [("precipitation", 200), ("precipitationQualityIndex", 1), ("randomError", 1000)]:
        array, fill = grid[name]
        value = float(array[column, row])
        if not math.isfinite(value) or value == fill or not 0 <= value <= maximum:
            raise ImergUnavailable()
        values[name] = value
    if values["precipitationQualityIndex"] == 0:
        raise ImergUnavailable()
    rad = math.pi / 180
    h = math.sin((lat-latitude)*rad/2)**2 + math.cos(latitude*rad)*math.cos(lat*rad)*math.sin((lon-longitude)*rad/2)**2
    return {"source": SOURCE, "precipitation_rate": values["precipitation"], "unit": "mm/h",
            "observed_at": start.isoformat(), "interval_end": end.isoformat(),
            "interval_minutes": 30, "spatial_resolution_degrees": 0.1,
            "granule": granule, "quality_index": values["precipitationQualityIndex"],
            "random_error_mm_h": values["randomError"],
            "distance_km": 6371*2*math.asin(math.sqrt(min(1, h))),
            "grid": {"row": row, "column": column, "latitude": lat, "longitude": lon},
            "quality_status": "Valid native rate and uncertainty; quality index > 0 (display policy)."}


class ImergService:
    """One global latest-grid cache per backend process, shared by all coordinates.

    Catalog checked at most every ten minutes; a granule downloaded/parsed once.
    Lock provides single flight, failures back off five minutes. Memory bounded
    to one grid (~78 MB) and one <=64 MB download; no persistent satellite files.
    FastAPI runs this synchronous endpoint in its worker thread pool.
    """
    def __init__(self):
        self._lock = Lock()
        self._catalog_until = 0
        self._failure_until = 0
        self._entry = None
        self._grid = None
        self._granule = None

    def _catalog(self, now, deadline):
        import json
        from urllib.parse import urlencode
        params = {"short_name": "GPM_3IMERGHHE", "version": "07", "sort_key": "-start_date", "page_size": 1,
                  "temporal": f"{(now-timedelta(hours=MAX_AGE_HOURS)).isoformat()},{now.isoformat()}"}
        entries = json.loads(_read(CMR_URL+"?"+urlencode(params), deadline, limit=1024*1024))["feed"]["entry"]
        if not entries:
            raise ImergUnavailable()
        return entries[0]

    def fetch(self, latitude, longitude):
        if (not math.isfinite(latitude) or not math.isfinite(longitude)
                or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
            raise ImergUnavailable()
        if not self._lock.acquire(timeout=35):
            raise ImergUnavailable()
        try:
            now = datetime.now(timezone.utc)
            if time.monotonic() < self._failure_until:
                raise ImergUnavailable()
            try:
                token = os.getenv("EARTHDATA_TOKEN", "").strip()
                if not token:
                    raise ImergUnavailable()
                deadline = time.monotonic()+30
                if time.monotonic() >= self._catalog_until:
                    self._entry = self._catalog(now, deadline)
                    self._catalog_until = time.monotonic()+CATALOG_SECONDS
                entry = self._entry
                url = next(link["href"] for link in entry["links"] if not link.get("inherited")
                           and link.get("rel", "").endswith("/data#") and link["href"].endswith(".HDF5"))
                granule = urlparse(url).path.rsplit("/", 1)[-1]
                if granule != self._granule:
                    grid = parse_granule(_download(url, token, deadline))
                    match = NAME.fullmatch(granule)
                    file_start = datetime.strptime(match[1]+match[2], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                    if (abs((_timestamp(entry["time_start"])-grid["start"]).total_seconds()) > 1
                            or abs((_timestamp(entry["time_end"])-grid["end"]).total_seconds()) > 1
                            or file_start != grid["start"]):
                        raise ImergUnavailable()
                    self._grid, self._granule = grid, granule
            except Exception:
                # Provider failures are never serialized/logged with credentials.
                self._failure_until = time.monotonic()+FAILURE_SECONDS
                raise ImergUnavailable() from None
            # A bad pixel does not poison valid pixels elsewhere in this grid.
            return select_observation(self._grid, latitude, longitude, self._granule, now)
        finally:
            self._lock.release()


imerg_service = ImergService()
