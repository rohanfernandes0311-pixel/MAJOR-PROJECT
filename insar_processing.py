"""
==============================================================
 InSAR / SAR Preprocessing Pipeline
==============================================================
Simulates the ESA SNAP (Sentinel Application Platform) workflow
for Sentinel-1 IW SLC processing.

Real SNAP XML Graph would execute:
  Apply-Orbit-File → TOPSAR-Split → Back-Geocoding →
  Interferogram → TOPSAR-Deburst → Goldstein-PhaseFiltering →
  SnaphuUnwrapping → Phase-to-Displacement → Terrain-Correction

This module provides:
  1. A Python wrapper that would call snappy / GPT (Graph Processing Tool)
  2. A pure-NumPy simulation of the outputs for offline/demo use
  3. Utilities to parse SNAPHU unwrapped phase files
  4. InSAR coherence and displacement extraction helpers
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Tuple, Optional
import warnings


# ─────────────────────────────────────────────────────────────
# 1.  SNAP GPT Graph Wrapper
# ─────────────────────────────────────────────────────────────

SNAP_GPT_GRAPH = """<?xml version="1.0" encoding="UTF-8"?>
<graph id="LandslideInSARGraph">
  <version>1.0</version>

  <!-- Step 1: Apply precise orbit files -->
  <node id="Apply-Orbit-File">
    <operator>Apply-Orbit-File</operator>
    <sources><sourceProduct refid="ReadMaster"/></sources>
    <parameters>
      <orbitType>Sentinel Precise (Auto Download)</orbitType>
      <polyDegree>3</polyDegree>
    </parameters>
  </node>

  <!-- Step 2: Split IW subswath -->
  <node id="TOPSAR-Split">
    <operator>TOPSAR-Split</operator>
    <sources><sourceProduct refid="Apply-Orbit-File"/></sources>
    <parameters>
      <subswath>IW2</subswath>
      <selectedPolarisations>VV</selectedPolarisations>
      <firstBurstIndex>1</firstBurstIndex>
      <lastBurstIndex>9</lastBurstIndex>
    </parameters>
  </node>

  <!-- Step 3: Back-geocoding for coregistration -->
  <node id="Back-Geocoding">
    <operator>Back-Geocoding</operator>
    <sources>
      <sourceProduct refid="TOPSAR-Split-Master"/>
      <sourceProduct refid="TOPSAR-Split-Slave"/>
    </sources>
    <parameters>
      <demName>SRTM 1Sec HGT</demName>
      <demResamplingMethod>BILINEAR_INTERPOLATION</demResamplingMethod>
      <resamplingType>BISINC_5_POINT_INTERPOLATION</resamplingType>
      <maskOutAreaWithoutElevation>true</maskOutAreaWithoutElevation>
    </parameters>
  </node>

  <!-- Step 4: Interferogram generation -->
  <node id="Interferogram">
    <operator>Interferogram</operator>
    <sources><sourceProduct refid="Back-Geocoding"/></sources>
    <parameters>
      <subtractFlatEarthPhase>true</subtractFlatEarthPhase>
      <srpPolynomialDegree>5</srpPolynomialDegree>
      <srpNumberPoints>501</srpNumberPoints>
      <orbitDegree>3</orbitDegree>
      <includeCoherence>true</includeCoherence>
    </parameters>
  </node>

  <!-- Step 5: Goldstein phase filtering -->
  <node id="GoldsteinPhaseFiltering">
    <operator>GoldsteinPhaseFiltering</operator>
    <sources><sourceProduct refid="Interferogram"/></sources>
    <parameters>
      <alpha>0.1</alpha>
      <FFTSizeString>64</FFTSizeString>
      <windowSizeString>3</windowSizeString>
      <useCoherenceMask>true</useCoherenceMask>
      <coherenceThreshold>0.2</coherenceThreshold>
    </parameters>
  </node>

  <!-- Step 6: Phase-to-Displacement -->
  <node id="PhaseToDisplacement">
    <operator>PhaseToDisplacement</operator>
    <sources><sourceProduct refid="GoldsteinPhaseFiltering"/></sources>
  </node>

  <!-- Step 7: Terrain Correction -->
  <node id="Terrain-Correction">
    <operator>Terrain-Correction</operator>
    <sources><sourceProduct refid="PhaseToDisplacement"/></sources>
    <parameters>
      <demName>SRTM 1Sec HGT</demName>
      <pixelSpacingInMeter>10.0</pixelSpacingInMeter>
      <mapProjection>AUTO:42001</mapProjection>
      <saveDEM>true</saveDEM>
      <saveLocalIncidenceAngle>true</saveLocalIncidenceAngle>
    </parameters>
  </node>
</graph>
"""


def run_snap_graph(master_slc: str, slave_slc: str, output_dir: str) -> Optional[str]:
    """
    Execute the SNAP GPT graph for InSAR processing.
    
    Args:
        master_slc  : Path to Sentinel-1 SLC master product (.zip / .SAFE)
        slave_slc   : Path to Sentinel-1 SLC slave product
        output_dir  : Directory for intermediate + final outputs
    
    Returns:
        Path to terrain-corrected displacement GeoTIFF, or None if SNAP not found.
    
    NOTE: Requires SNAP to be installed and `gpt` on PATH.
          Install from: https://step.esa.int/main/toolboxes/snap/
    """
    import subprocess, tempfile, os

    # Write graph to temp file
    graph_path = Path(tempfile.mktemp(suffix=".xml"))
    graph_path.write_text(SNAP_GPT_GRAPH)

    output_path = Path(output_dir) / "displacement_tc.tif"

    cmd = [
        "gpt", str(graph_path),
        "-PmasterFile=" + master_slc,
        "-PslaveFile="  + slave_slc,
        "-t", str(output_path),
        "-f", "GeoTIFF"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode == 0:
            print(f"✅ SNAP processing complete → {output_path}")
            return str(output_path)
        else:
            print(f"❌ SNAP error:\n{result.stderr}")
            return None
    except FileNotFoundError:
        warnings.warn("SNAP GPT not found on PATH. Using simulated InSAR data.")
        return None
    except subprocess.TimeoutExpired:
        print("❌ SNAP processing timed out (> 1 hour)")
        return None


# ─────────────────────────────────────────────────────────────
# 2.  Pure-NumPy InSAR Simulation (offline / demo mode)
# ─────────────────────────────────────────────────────────────

def simulate_insar_stack(
    n_pixels: int = 200,
    n_dates : int = 24,
    seed    : int = 42
) -> Tuple[np.ndarray, np.ndarray, pd.DatetimeIndex]:
    """
    Simulate an InSAR displacement time-series stack.
    
    Returns:
        displacement : (n_pixels, n_dates) array in mm
        coherence    : (n_pixels, n_dates) coherence values [0-1]
        dates        : DatetimeIndex of acquisition dates (12-day repeat)
    """
    rng   = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-01", periods=n_dates, freq="12D")

    # Pixel categories: stable, slow creep, accelerating, seasonal
    stable       = rng.integers(0, n_pixels, int(n_pixels * 0.50))
    creep        = rng.integers(0, n_pixels, int(n_pixels * 0.30))
    accelerating = rng.integers(0, n_pixels, int(n_pixels * 0.10))
    seasonal_pix = rng.integers(0, n_pixels, int(n_pixels * 0.10))

    displacement = np.zeros((n_pixels, n_dates))

    t = np.arange(n_dates)

    # Stable: small noise only
    displacement[stable, :]       += rng.normal(0, 0.5, (len(stable), n_dates))

    # Linear creep: 2–10 mm/yr
    rate = rng.uniform(2, 10, len(creep)) / (365 / 12)
    displacement[creep, :]        += np.outer(rate, t) + rng.normal(0, 1, (len(creep), n_dates))

    # Accelerating (pre-failure): exponential increase
    for px in accelerating:
        start_accel = rng.integers(n_dates // 2, n_dates - 3)
        displacement[px, :]       += t * rng.uniform(0.5, 2)
        displacement[px, start_accel:] *= np.exp(
            np.linspace(0, rng.uniform(1, 3), n_dates - start_accel)
        )
        displacement[px, :]       += rng.normal(0, 2, n_dates)

    # Seasonal (rainfall-driven): sinusoidal
    for px in seasonal_pix:
        amplitude = rng.uniform(3, 15)
        phase     = rng.uniform(0, 2 * np.pi)
        displacement[px, :] += amplitude * np.sin(2 * np.pi * t / 30.4 + phase)
        displacement[px, :] += rng.normal(0, 1, n_dates)

    # Coherence: degrades with moisture, recovers on dry periods
    coherence = rng.beta(5, 2, (n_pixels, n_dates))  # base: good coherence
    seasonal_loss = 0.2 * np.sin(2 * np.pi * t / 30.4)
    coherence -= seasonal_loss[np.newaxis, :]
    coherence  = coherence.clip(0.1, 0.99)

    return displacement, coherence, dates


# ─────────────────────────────────────────────────────────────
# 3.  Inverse Velocity Method (IVM) — Fukuzono (1985)
# ─────────────────────────────────────────────────────────────

def inverse_velocity_method(
    displacement: np.ndarray,
    dt_days     : float = 12.0,
    window      : int   = 5,
    project_steps: int  = 10
) -> dict:
    """
    Applies the Inverse Velocity Method (IVM) to predict failure time.
    
    The IVM (Fukuzono 1985; Voight 1988) linearises accelerating creep:
        1/v → 0  as  t → t_failure (rupture time)
    
    Args:
        displacement : 1D array of cumulative LOS displacement (mm), sorted by time
        dt_days      : Time step between acquisitions (days)
        window       : Rolling window for velocity smoothing
        project_steps: Number of future steps to project
    
    Returns:
        dict with velocity, inverse_velocity, projected_failure_day, alert_level
    """
    disp = np.asarray(displacement, dtype=float)
    n    = len(disp)

    # Instantaneous velocity (mm / day)
    velocity = np.gradient(disp) / dt_days
    velocity[velocity <= 0] = 1e-6   # avoid division by zero / negative

    # Rolling mean velocity
    smooth_v = pd.Series(velocity).rolling(window, min_periods=1).mean().values

    # Inverse velocity
    inv_v = 1.0 / smooth_v

    # Linear regression on last portion to find failure intercept
    n_fit  = max(window, n // 3)
    x_fit  = np.arange(n - n_fit, n, dtype=float)
    y_fit  = inv_v[n - n_fit:]

    valid  = np.isfinite(y_fit)
    if valid.sum() < 3:
        return {"error": "Insufficient data for IVM regression"}

    m, b   = np.polyfit(x_fit[valid], y_fit[valid], 1)

    # t_failure when inv_v → 0  →  t = -b/m
    failure_step = -b / m if m < 0 else np.inf
    failure_day  = (failure_step - n) * dt_days  # days from now

    # Project future inverse velocity
    x_proj = np.arange(n, n + project_steps, dtype=float)
    inv_v_proj = m * x_proj + b

    # Alert level based on projected failure
    if   failure_day < 3:
        alert = "CRITICAL"
    elif failure_day < 14:
        alert = "HIGH"
    elif failure_day < 60:
        alert = "MEDIUM"
    else:
        alert = "LOW"

    return {
        "velocity"          : velocity,
        "smooth_velocity"   : smooth_v,
        "inverse_velocity"  : inv_v,
        "inv_v_projected"   : inv_v_proj,
        "slope_m"           : m,
        "intercept_b"       : b,
        "failure_day_est"   : failure_day,
        "alert_level"       : alert,
    }


# ─────────────────────────────────────────────────────────────
# 4.  Deformation Feature Extractor
# ─────────────────────────────────────────────────────────────

def extract_insar_features(
    displacement : np.ndarray,   # shape: (n_pixels, n_dates)
    coherence    : np.ndarray,   # shape: (n_pixels, n_dates)
    dt_days      : float = 12.0
) -> pd.DataFrame:
    """
    Compute per-pixel statistical features from InSAR time-series.
    
    Features derived:
      - mean_deformation      : Temporal mean displacement
      - std_deformation       : Temporal std (noise / variability)
      - max_deformation       : Peak displacement
      - mean_velocity         : Mean LOS velocity (mm/day)
      - velocity_trend        : Linear trend of velocity (acceleration proxy)
      - mean_coherence        : Mean coherence
      - min_coherence         : Minimum coherence (quality flag)
      - ivm_slope             : IVM regression slope (Voight param)
      - estimated_failure_day : IVM failure estimate
    """
    n_pixels, n_dates = displacement.shape
    records = []

    for i in range(n_pixels):
        d = displacement[i]
        c = coherence[i]

        velocity = np.gradient(d) / dt_days
        # Linear trend of velocity = acceleration
        vel_trend = np.polyfit(np.arange(n_dates), velocity, 1)[0]

        ivm = inverse_velocity_method(d, dt_days=dt_days)

        records.append({
            "pixel_id"            : i,
            "mean_deformation_mm" : d.mean(),
            "std_deformation_mm"  : d.std(),
            "max_deformation_mm"  : d.max(),
            "mean_velocity_mm_d"  : velocity.mean(),
            "velocity_trend"      : vel_trend,
            "mean_coherence"      : c.mean(),
            "min_coherence"       : c.min(),
            "ivm_slope"           : ivm.get("slope_m", np.nan),
            "est_failure_days"    : ivm.get("failure_day_est", 9999),
        })

    return pd.DataFrame(records)


if __name__ == "__main__":
    print("Running InSAR simulation...")
    disp, coh, dates = simulate_insar_stack(n_pixels=50, n_dates=24)
    features_df      = extract_insar_features(disp, coh)
    print(features_df.head(10).to_string())

    # Demo IVM on one accelerating pixel
    ivm_result = inverse_velocity_method(disp[5])
    print(f"\nIVM Alert Level : {ivm_result['alert_level']}")
    print(f"Est. Failure    : {ivm_result['failure_day_est']:.1f} days")
