# Critical-pixel selection: validation required

The dashboard selects a deformation row and uses its identifier to index a time series from `simulate_insar_stack(n_pixels=100)`. That stack is simulated and does not establish a geographic or data-row correspondence.

## Index semantics

- `Series.idxmax()` returns the dataframe index label. `np.nanargmax(series.to_numpy())` returns the position in the current row order.
- The dashboard currently loads the CSV with `pandas.read_csv()` and does not filter or reorder it before selection, so the current index is the default zero-based `RangeIndex`. The label and position currently agree.
- With a non-contiguous or reordered index, a label is not necessarily the row position. Using the position is appropriate only when the consumer indexes an array in the same row order; that alignment must be tested and documented.

## Missing and empty inputs

- Both `idxmax()` and `nanargmax()` select a maximum while ignoring partial NaNs by default.
- `nanargmax()` raises `ValueError` for an empty or all-NaN array. With `idxmax()`, an all-NaN series yields a missing label that fails when converted to `int`; empty input likewise has no valid selection. Neither path currently represents an unavailable estimate safely.
- A future change should explicitly handle no finite deformation values and avoid showing an estimate as valid in that case.

## Mapping limitation

The dataset contains 5,000 rows while the dashboard creates a 100-pixel simulated InSAR stack. The selected row is reduced modulo 100 to index the simulated stack. No coordinate join or verified mapping connects those rows to those simulated pixels. The inverse-velocity estimate is therefore not geographically validated.

## Required validation before changing selection logic

1. Add tests for a default index, non-contiguous labels, reordered rows, partial NaNs, all-NaN data, and empty input.
2. Verify any dataset-row to InSAR-pixel mapping from source data and coordinates; remove the modulo assumption unless a documented mapping justifies it.
3. Make unavailable/invalid input produce an explicitly unavailable estimate, then verify dashboard presentation does not imply a location-linked forecast.
