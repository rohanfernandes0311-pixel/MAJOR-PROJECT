"""
Builds ML-ready dataset for the Landslide Early Warning System.

Phase 1 requirement support:
  1) Real Indian-region CSVs (Raigad, rainfall, soil moisture) when available
  2) Synthetic fallback dataset when CSVs are not available
  3) Missing-value handling and normalized-feature export

Outputs:
  data/landslide_dataset.csv
  data/landslide_dataset_normalized.csv
"""

import argparse
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler


FEATURES = [
    "deformation_mm", "velocity_mm_yr", "coherence",
    "rainfall_mm", "slope_deg", "soil_moisture_pct",
    "elevation_m", "aspect_deg", "ndvi",
]

INDIAN_REGIONS = [
    "Raigad", "Pune", "Satara", "Ratnagiri", "Sindhudurg",
    "Idukki", "Wayanad", "Nilgiris", "Darjeeling", "Sikkim",
]


def _read_csv_optional(path_str: str | None, name: str) -> pd.DataFrame | None:
    if not path_str:
        return None
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"{name} CSV not found: {path}")
    return pd.read_csv(path)


def _find_first_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def _series_from_any(
    dfs: list[pd.DataFrame | None],
    candidates: list[str],
    n: int,
    rng: np.random.Generator,
    synth_fn: Callable[[np.random.Generator, int], np.ndarray],
) -> np.ndarray:
    for df in dfs:
        if df is None:
            continue
        col = _find_first_column(df, candidates)
        if col is None:
            continue
        values = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
        if values.size == 0:
            continue
        values = np.resize(values, n)
        return values
    return synth_fn(rng, n)


def _build_synthetic(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    slope_deg = rng.beta(2, 5, n) * 60
    elevation_m = rng.normal(1200, 400, n).clip(100, 3000)
    aspect_deg = rng.uniform(0, 360, n)
    ndvi = np.subtract(rng.beta(3, 2, n) * 2.0, 1.0)

    day_of_year = rng.integers(1, 366, n)
    day_centered = np.subtract(day_of_year, 90)
    seasonal_factor = 1 + 0.6 * np.sin(2 * np.pi * day_centered / 365)
    rainfall_mm = (rng.exponential(30, n) * seasonal_factor).clip(0, 350)

    soil_moisture_pct = (
        20 + 0.3 * rainfall_mm + 0.2 * slope_deg + rng.normal(0, 5, n)
    ).clip(5, 95)

    base_deformation = (
        0.1 * slope_deg
        + 0.05 * soil_moisture_pct
        + 0.02 * rainfall_mm
        + rng.normal(0, 3, n)
    )
    deformation_mm = base_deformation * rng.lognormal(0, 0.4, n)
    velocity_mm_yr = deformation_mm * rng.uniform(3, 8, n)

    coherence = (
        0.9
        - 0.003 * rainfall_mm
        - 0.005 * np.clip(ndvi, 0, None)
        + rng.normal(0, 0.05, n)
    ).clip(0.1, 0.99)

    df = pd.DataFrame(
        {
            "region": rng.choice(INDIAN_REGIONS, n),
            "deformation_mm": deformation_mm,
            "velocity_mm_yr": velocity_mm_yr,
            "coherence": coherence,
            "rainfall_mm": rainfall_mm,
            "slope_deg": slope_deg,
            "soil_moisture_pct": soil_moisture_pct,
            "elevation_m": elevation_m,
            "aspect_deg": aspect_deg,
            "ndvi": ndvi,
            "day_of_year": day_of_year,
            "latitude": rng.uniform(9.5, 20.5, n),
            "longitude": rng.uniform(72.5, 78.5, n),
        }
    )
    return df


def _build_from_indian_csvs(
    raigad_df: pd.DataFrame | None,
    rainfall_df: pd.DataFrame | None,
    soil_df: pd.DataFrame | None,
    fallback_n: int,
    seed: int,
) -> pd.DataFrame:
    if raigad_df is None and rainfall_df is None and soil_df is None:
        return _build_synthetic(fallback_n, seed)

    rng = np.random.default_rng(seed)

    base_df: pd.DataFrame | None = None
    for candidate_df in (raigad_df, rainfall_df, soil_df):
        if candidate_df is not None:
            base_df = candidate_df
            break

    if base_df is None:
        return _build_synthetic(fallback_n, seed)

    n = len(base_df)
    dfs = [raigad_df, rainfall_df, soil_df, base_df]

    rainfall_mm = _series_from_any(
        dfs,
        ["rainfall_mm", "rainfall", "precip_mm", "precipitation", "rain_mm"],
        n,
        rng,
        lambda r, m: r.exponential(35, m).clip(0, 350),
    )
    slope_deg = _series_from_any(
        dfs,
        ["slope_deg", "slope", "slope_degree"],
        n,
        rng,
        lambda r, m: r.beta(2, 5, m) * 60,
    )
    soil_moisture_pct = _series_from_any(
        dfs,
        ["soil_moisture_pct", "soil_moisture", "sm_pct", "soil_pct"],
        n,
        rng,
        lambda r, m: (20 + 0.3 * rainfall_mm + r.normal(0, 6, m)).clip(5, 95),
    )
    deformation_mm = _series_from_any(
        dfs,
        ["deformation_mm", "displacement_mm", "los_displacement_mm"],
        n,
        rng,
        lambda r, m: (0.1 * slope_deg + 0.02 * rainfall_mm + r.normal(0, 4, m)),
    )
    velocity_mm_yr = _series_from_any(
        dfs,
        ["velocity_mm_yr", "velocity", "los_velocity_mm_yr"],
        n,
        rng,
        lambda r, m: deformation_mm * r.uniform(2.5, 8.5, m),
    )
    coherence = _series_from_any(
        dfs,
        ["coherence", "insar_coherence"],
        n,
        rng,
        lambda r, m: (0.9 - 0.003 * rainfall_mm + r.normal(0, 0.06, m)).clip(0.1, 0.99),
    )
    elevation_m = _series_from_any(
        dfs,
        ["elevation_m", "elevation", "dem", "altitude"],
        n,
        rng,
        lambda r, m: r.normal(1100, 350, m).clip(100, 3000),
    )
    aspect_deg = _series_from_any(
        dfs,
        ["aspect_deg", "aspect"],
        n,
        rng,
        lambda r, m: r.uniform(0, 360, m),
    )
    ndvi = _series_from_any(
        dfs,
        ["ndvi", "vegetation_index"],
        n,
        rng,
        lambda r, m: np.subtract(r.beta(3, 2, m) * 2.0, 1.0),
    )

    lat = _series_from_any(
        dfs,
        ["latitude", "lat"],
        n,
        rng,
        lambda r, m: r.uniform(17.6, 19.3, m),
    )
    lon = _series_from_any(
        dfs,
        ["longitude", "lon", "lng"],
        n,
        rng,
        lambda r, m: r.uniform(72.6, 74.2, m),
    )

    region_col = _find_first_column(base_df, ["district", "region", "location", "state"])
    if region_col is not None:
        region_values = base_df[region_col].astype(str).to_numpy()
        region_values = np.resize(region_values, n)
    else:
        region_values = rng.choice(INDIAN_REGIONS, n)

    day_of_year = _series_from_any(
        dfs,
        ["day_of_year", "doy"],
        n,
        rng,
        lambda r, m: r.integers(1, 366, m),
    )

    df = pd.DataFrame(
        {
            "region": region_values,
            "deformation_mm": deformation_mm,
            "velocity_mm_yr": velocity_mm_yr,
            "coherence": coherence,
            "rainfall_mm": rainfall_mm,
            "slope_deg": slope_deg,
            "soil_moisture_pct": soil_moisture_pct,
            "elevation_m": elevation_m,
            "aspect_deg": aspect_deg,
            "ndvi": ndvi,
            "day_of_year": day_of_year,
            "latitude": lat,
            "longitude": lon,
        }
    )
    return df


def _finalize_labels_and_clean(df: pd.DataFrame) -> pd.DataFrame:
    for col in FEATURES + ["latitude", "longitude", "day_of_year"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in FEATURES + ["latitude", "longitude", "day_of_year"]:
        med = float(df[col].median()) if not np.isnan(df[col].median()) else 0.0
        df[col] = df[col].fillna(med)

    deformation = df["deformation_mm"].to_numpy(dtype=float)
    velocity = df["velocity_mm_yr"].to_numpy(dtype=float)
    rainfall = df["rainfall_mm"].to_numpy(dtype=float)
    slope = df["slope_deg"].to_numpy(dtype=float)
    soil_moisture = df["soil_moisture_pct"].to_numpy(dtype=float)
    coherence = df["coherence"].to_numpy(dtype=float)

    risk_score = (
        0.28 * (deformation / max(float(np.max(deformation)), 1e-9))
        + 0.18 * (velocity / max(float(np.max(velocity)), 1e-9))
        + 0.18 * (rainfall / max(float(np.max(rainfall)), 1e-9))
        + 0.14 * (slope / max(float(np.max(slope)), 1e-9))
        + 0.12 * (soil_moisture / max(float(np.max(soil_moisture)), 1e-9))
        - 0.10 * coherence
    )

    bins = [-np.inf, 0.33, 0.60, np.inf]
    labels = [0, 1, 2]
    df["label"] = pd.cut(risk_score, bins=bins, labels=labels).astype(int)
    df["risk_level"] = df["label"].map({0: "Low", 1: "Medium", 2: "High"})

    for col in FEATURES:
        df[col] = df[col].astype(float)

    df["day_of_year"] = df["day_of_year"].round().astype(int)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Build landslide dataset (Indian CSVs or synthetic fallback)")
    parser.add_argument("--raigad-csv", type=str, default=None, help="Path to Raigad landslide CSV")
    parser.add_argument("--rainfall-csv", type=str, default=None, help="Path to India rainfall CSV")
    parser.add_argument("--soil-csv", type=str, default=None, help="Path to soil moisture CSV")
    parser.add_argument("--n-synthetic", type=int, default=5000, help="Rows when synthetic fallback is used")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    raigad_df = _read_csv_optional(args.raigad_csv, "Raigad")
    rainfall_df = _read_csv_optional(args.rainfall_csv, "Rainfall")
    soil_df = _read_csv_optional(args.soil_csv, "Soil moisture")

    df = _build_from_indian_csvs(
        raigad_df=raigad_df,
        rainfall_df=rainfall_df,
        soil_df=soil_df,
        fallback_n=args.n_synthetic,
        seed=args.seed,
    )
    df = _finalize_labels_and_clean(df)

    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(df[FEATURES])
    df_norm = df.copy()
    df_norm[FEATURES] = np.round(scaled, 6)

    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(exist_ok=True)
    raw_path = data_dir / "landslide_dataset.csv"
    norm_path = data_dir / "landslide_dataset_normalized.csv"

    df.to_csv(raw_path, index=False)
    df_norm.to_csv(norm_path, index=False)

    print(f"Dataset saved: {raw_path}")
    print(f"Normalized dataset saved: {norm_path}")
    print(f"Rows: {len(df)}")
    print("Label distribution:")
    print(df["risk_level"].value_counts().to_string())


if __name__ == "__main__":
    main()
