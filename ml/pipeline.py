from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.common import (
    RANDOM_SEED,
    ModelBundle,
    environment_metadata,
    finite_or_none,
    fit_calibrator,
    global_and_local_explanations,
    metrics,
    now,
    population_stability_index,
    sha256,
    write_csv,
    write_json,
    choose_threshold,
)
from ml.estimators import RuleEstimator


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MODEL_READY = DATA / "model_ready"
METADATA = DATA / "metadata"
ARTIFACTS = ROOT / "ml" / "artifacts"
REPORTS = ROOT / "ml" / "reports"
RUN_VERSION = "1.1.0"
TARGETS = json.loads((ROOT / "ml" / "config" / "targets.json").read_text(encoding="utf-8"))
ACCEPTANCE = json.loads((ROOT / "ml" / "config" / "acceptance.json").read_text(encoding="utf-8"))


FEATURES: dict[str, list[str]] = {
    "drought": [
        "rain_7d_mm", "rain_30d_mm", "rain_90d_mm", "heavy_rain_days_30d",
        "dry_spell_days", "t2m_7d_c", "t2m_30d_c", "t2m_max_30d_c",
        "gwet_top_7d", "gwet_top_30d", "gwet_root_30d", "ndvi_last",
        "evi_last", "ndvi_change_1", "vegetation_valid_pixel_fraction",
        "ndvi_last_anomaly_z_reference",
    ],
    "flood": [
        "current_level_m", "level_change_1d", "level_change_3d", "level_change_7d",
        "level_mean_7d", "level_max_7d", "level_ratio_moderate",
        "distance_to_moderate_m", "distance_to_high_m", "distance_to_bankfull_m",
        "rain_1d_mm", "rain_3d_mm", "rain_7d_mm", "rain_30d_mm",
        "heavy_rain_days_7d", "gwet_top_7d", "gwet_top_30d", "gwet_root_30d",
        "t2m_7d_c",
    ],
    "food_security": [
        "rain_30d_mm", "rain_90d_mm", "dry_days_30d", "t2m_30d_c",
        "t2m_max_30d_c", "gwet_top_30d", "gwet_root_30d", "ndvi_last",
        "ndvi_change", "vegetation_valid_pixel_fraction", "market_usdkg_90d_median",
        "market_price_change_previous_90d", "market_price_anomaly_365d",
        "previous_ipc3plus_percentage", "log_region_population",
    ],
}


SPLITS = {
    "drought": {"train": (2015, 2020), "validation": (2021, 2022), "test": (2023, 2025)},
    "flood": {"train": (2015, 2020), "validation": (2021, 2022), "test": (2023, 2025)},
    "food_security": {"train": (2017, 2021), "validation": (2022, 2023), "test": (2024, 2025)},
}


def _rolling_sum(frame: pd.DataFrame, column: str, windows: list[int], prefix: str) -> pd.DataFrame:
    frame = frame.sort_values(["district_id", "date"]).copy()
    grouped = frame.groupby("district_id", sort=False)[column]
    for window in windows:
        frame[f"{prefix}_{window}d"] = grouped.transform(
            lambda values: values.rolling(window, min_periods=window).sum()
        )
    return frame


def _climate_daily() -> tuple[pd.DataFrame, pd.DataFrame]:
    rain = pd.read_csv(
        DATA / "processed" / "rainfall" / "chirps_v3_daily_district_2015-01-01_2025-12-31.csv",
        usecols=["district_id", "region_id", "date", "rainfall_mean_mm", "heavy_rain_20mm", "dry_spell_days"],
    )
    rain["date"] = pd.to_datetime(rain["date"])
    rain = _rolling_sum(rain, "rainfall_mean_mm", [3, 7, 30, 90], "rain")
    rain["heavy_rain_days_7d"] = rain.groupby("district_id", sort=False)["heavy_rain_20mm"].transform(
        lambda values: values.rolling(7, min_periods=7).sum()
    )
    rain["heavy_rain_days_30d"] = rain.groupby("district_id", sort=False)["heavy_rain_20mm"].transform(
        lambda values: values.rolling(30, min_periods=30).sum()
    )
    power = pd.read_csv(DATA / "processed" / "climate" / "nasa_power_district_daily_20000101_20251231.csv.gz")
    power["date"] = pd.to_datetime(power["date"])
    power = power[power["date"].between("2014-09-01", "2025-12-31")].sort_values(["district_id", "date"])
    for column, output, reducer in [
        ("t2m_c", "t2m_7d_c", "mean"), ("t2m_c", "t2m_30d_c", "mean"),
        ("t2m_max_c", "t2m_max_30d_c", "max"),
        ("gwet_top_relative", "gwet_top_7d", "mean"),
        ("gwet_top_relative", "gwet_top_30d", "mean"),
        ("gwet_root_relative", "gwet_root_30d", "mean"),
    ]:
        window = 7 if "7d" in output else 30
        grouped = power.groupby("district_id", sort=False)[column]
        roller = grouped.transform(lambda values, w=window: values.rolling(w, min_periods=w).mean())
        if reducer == "max":
            roller = grouped.transform(lambda values, w=window: values.rolling(w, min_periods=w).max())
        power[output] = roller
    return rain, power


def build_drought_dataset(rain: pd.DataFrame, power: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    vegetation = pd.read_csv(
        DATA / "processed" / "vegetation" / "mod13q1_v061_district_2015-01-01_2025-12-31.csv"
    )
    vegetation["date"] = pd.to_datetime(vegetation["date"])
    vegetation = vegetation.sort_values(["district_id", "date"]).copy()
    vegetation["seasonal_slot"] = ((vegetation["date"].dt.dayofyear - 1) // 16 + 1).astype(int)
    reference = (
        vegetation[vegetation["date"].dt.year.between(2015, 2020)]
        .groupby(["district_id", "seasonal_slot"])["ndvi_mean"]
        .agg(["mean", "std", "count"])
        .reset_index()
        .rename(columns={"mean": "ndvi_reference_mean", "std": "ndvi_reference_std", "count": "ndvi_reference_count"})
    )
    vegetation = vegetation.merge(reference, on=["district_id", "seasonal_slot"], how="left")
    vegetation["ndvi_anomaly_z_reference"] = (
        (vegetation["ndvi_mean"] - vegetation["ndvi_reference_mean"])
        / vegetation["ndvi_reference_std"].replace(0, np.nan)
    )
    grouped = vegetation.groupby("district_id", sort=False)
    vegetation["target_period_start"] = grouped["date"].shift(-1)
    vegetation["target_ndvi_anomaly_z"] = grouped["ndvi_anomaly_z_reference"].shift(-1)
    vegetation["target_ndvi_mean"] = grouped["ndvi_mean"].shift(-1)
    vegetation["target_gap_days"] = (vegetation["target_period_start"] - vegetation["date"]).dt.days
    vegetation["target"] = (vegetation["target_ndvi_anomaly_z"] <= -1.0).astype("Int64")
    vegetation.loc[vegetation["target_ndvi_anomaly_z"].isna(), "target"] = pd.NA
    vegetation["feature_as_of_date"] = vegetation["target_period_start"] - pd.Timedelta(days=1)
    vegetation["vegetation_feature_timestamp"] = vegetation["date"] + pd.Timedelta(days=15)
    vegetation["ndvi_last"] = vegetation["ndvi_mean"]
    vegetation["ndvi_last_anomaly_z_reference"] = vegetation["ndvi_anomaly_z_reference"]
    vegetation["evi_last"] = vegetation["evi_mean"]
    vegetation["ndvi_change_1"] = grouped["ndvi_mean"].diff()
    frame = vegetation[
        vegetation["target"].notna() & vegetation["target_gap_days"].between(15, 17)
    ].copy()
    rain_columns = [
        "district_id", "date", "rain_7d", "rain_30d", "rain_90d",
        "heavy_rain_days_30d", "dry_spell_days",
    ]
    power_columns = [
        "district_id", "date", "t2m_7d_c", "t2m_30d_c", "t2m_max_30d_c",
        "gwet_top_7d", "gwet_top_30d", "gwet_root_30d",
    ]
    frame = frame.merge(
        rain[rain_columns], left_on=["district_id", "feature_as_of_date"], right_on=["district_id", "date"], how="left", suffixes=("", "_rain")
    ).drop(columns=["date_rain"])
    frame = frame.merge(
        power[power_columns], left_on=["district_id", "feature_as_of_date"], right_on=["district_id", "date"], how="left", suffixes=("", "_power")
    ).drop(columns=["date_power"])
    frame = frame.rename(columns={
        "rain_7d": "rain_7d_mm", "rain_30d": "rain_30d_mm", "rain_90d": "rain_90d_mm",
        "valid_pixel_fraction": "vegetation_valid_pixel_fraction",
    })
    frame["rainfall_feature_timestamp"] = frame["feature_as_of_date"]
    frame["power_feature_timestamp"] = frame["feature_as_of_date"]
    frame["target_period_end"] = frame["target_period_start"] + pd.Timedelta(days=15)
    frame["target"] = frame["target"].astype(int)
    keep = [
        "district_id", "district_name", "region_id", "region_name", "feature_as_of_date",
        "target_period_start", "target_period_end", "target", "target_ndvi_anomaly_z",
        "target_ndvi_mean", "vegetation_feature_timestamp", "rainfall_feature_timestamp",
        "power_feature_timestamp", *FEATURES["drought"],
    ]
    frame = frame[keep].sort_values(["target_period_start", "district_id"]).reset_index(drop=True)
    return frame, {"label_unknown_rows": int(vegetation["target"].isna().sum()), "excluded_non_16_day_gaps": int((vegetation["target"].notna() & ~vegetation["target_gap_days"].between(15, 17)).sum())}


def build_flood_dataset(rain: pd.DataFrame, power: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    river = pd.read_csv(DATA / "processed" / "river_levels" / "river_levels_canonical.csv")
    station = pd.read_csv(DATA / "processed" / "river_station_metadata.csv")
    river["date"] = pd.to_datetime(river["date"])
    river = river[river["date"].between("2015-01-01", "2025-12-31")]
    river = river.sort_values(["station_id", "date", "id"]).drop_duplicates(["station_id", "date"], keep="last")
    outputs = []
    unknown = 0
    for station_code, source in river.groupby("station_id"):
        source = source.set_index("date").sort_index()
        calendar = pd.date_range(max(source.index.min(), pd.Timestamp("2015-01-01")), min(source.index.max(), pd.Timestamp("2025-12-31")), freq="D")
        daily = source.reindex(calendar)
        daily.index.name = "feature_as_of_date"
        daily["station_code"] = station_code
        metadata = station.loc[station["station_code"] == station_code].iloc[0]
        for field in ["moderate_threshold_m", "high_threshold_m", "bankfull_threshold_m", "canonical_district_id", "river"]:
            daily[field] = metadata[field]
        daily["current_level_m"] = daily["level_m"]
        daily["level_change_1d"] = daily["level_m"] - daily["level_m"].shift(1)
        daily["level_change_3d"] = daily["level_m"] - daily["level_m"].shift(3)
        daily["level_change_7d"] = daily["level_m"] - daily["level_m"].shift(7)
        daily["level_mean_7d"] = daily["level_m"].rolling(7, min_periods=7).mean()
        daily["level_max_7d"] = daily["level_m"].rolling(7, min_periods=7).max()
        daily["level_ratio_moderate"] = daily["level_m"] / daily["moderate_threshold_m"]
        daily["distance_to_moderate_m"] = daily["moderate_threshold_m"] - daily["level_m"]
        daily["distance_to_high_m"] = daily["high_threshold_m"] - daily["level_m"]
        daily["distance_to_bankfull_m"] = daily["bankfull_threshold_m"] - daily["level_m"]
        futures = pd.concat([daily["level_m"].shift(-day).rename(day) for day in (1, 2, 3)], axis=1)
        daily["target_future_max_level_m"] = futures.max(axis=1)
        daily["future_window_complete"] = futures.notna().all(axis=1)
        daily["target"] = (daily["target_future_max_level_m"] >= daily["moderate_threshold_m"]).astype("Int64")
        daily.loc[~daily["future_window_complete"], "target"] = pd.NA
        crossing = pd.DataFrame({day: futures[day] >= daily["moderate_threshold_m"] for day in (1, 2, 3)})
        daily["target_first_crossing_lead_days"] = crossing.apply(
            lambda row: next((int(day) for day in (1, 2, 3) if bool(row[day])), np.nan), axis=1
        )
        unknown += int(daily["target"].isna().sum())
        outputs.append(daily.reset_index())
    frame = pd.concat(outputs, ignore_index=True)
    frame = frame[frame["target"].notna() & frame["level_mean_7d"].notna()].copy()
    frame["target_period_start"] = frame["feature_as_of_date"] + pd.Timedelta(days=1)
    frame["target_period_end"] = frame["feature_as_of_date"] + pd.Timedelta(days=3)
    rain_columns = [
        "district_id", "date", "rainfall_mean_mm", "rain_3d", "rain_7d", "rain_30d", "heavy_rain_days_7d",
    ]
    power_columns = ["district_id", "date", "t2m_7d_c", "gwet_top_7d", "gwet_top_30d", "gwet_root_30d"]
    frame = frame.merge(
        rain[rain_columns], left_on=["canonical_district_id", "feature_as_of_date"], right_on=["district_id", "date"], how="left"
    ).drop(columns=["district_id", "date"])
    frame = frame.merge(
        power[power_columns], left_on=["canonical_district_id", "feature_as_of_date"], right_on=["district_id", "date"], how="left"
    ).drop(columns=["district_id", "date"])
    frame = frame.rename(columns={
        "rainfall_mean_mm": "rain_1d_mm", "rain_3d": "rain_3d_mm", "rain_7d": "rain_7d_mm", "rain_30d": "rain_30d_mm"
    })
    frame["river_feature_timestamp"] = frame["feature_as_of_date"]
    frame["rainfall_feature_timestamp"] = frame["feature_as_of_date"]
    frame["power_feature_timestamp"] = frame["feature_as_of_date"]
    frame["target"] = frame["target"].astype(int)
    keep = [
        "station_code", "canonical_district_id", "river", "feature_as_of_date",
        "target_period_start", "target_period_end", "target", "target_future_max_level_m",
        "target_first_crossing_lead_days", "moderate_threshold_m", "high_threshold_m",
        "bankfull_threshold_m", "river_feature_timestamp", "rainfall_feature_timestamp",
        "power_feature_timestamp", *FEATURES["flood"],
    ]
    frame = frame[keep].sort_values(["feature_as_of_date", "station_code"]).reset_index(drop=True)
    return frame, {"unknown_future_windows": unknown, "scope": sorted(frame["station_code"].unique())}


def _ipc_region_mapping() -> dict[str, str]:
    crosswalk = pd.read_csv(METADATA / "geographic_crosswalk.csv")
    rows = crosswalk[(crosswalk["source_dataset"] == "ipc_hdx") & (crosswalk["geography_level"] == "region")]
    return dict(zip(rows["source_name"].astype(str).str.strip(), rows["canonical_id"]))


def build_food_dataset(rain: pd.DataFrame, power: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    ipc = pd.read_csv(DATA / "processed" / "food_security" / "ipc_outcomes_canonical.csv")
    ipc = ipc[
        ipc["source_file"].str.contains("level1", case=False, na=False)
        & ipc["assessment_period_type"].eq("current")
        & ipc["Phase"].astype(str).eq("3+")
    ].copy()
    ipc["target_period_start"] = pd.to_datetime(ipc["From"])
    ipc["target_period_end"] = pd.to_datetime(ipc["To"])
    ipc = ipc[ipc["target_period_start"] <= "2025-12-31"]
    mapping = _ipc_region_mapping()
    ipc["region_name_source"] = ipc["Level 1"].astype(str)
    ipc["region_id"] = ipc["region_name_source"].str.strip().map(mapping)
    unresolved = int(ipc["region_id"].isna().sum())
    ipc = ipc[ipc["region_id"].notna()].copy()
    ipc["target_ipc3plus_percentage"] = pd.to_numeric(ipc["Percentage"], errors="coerce")
    ipc["target"] = (ipc["target_ipc3plus_percentage"] >= 0.20).astype(int)
    ipc["feature_as_of_date"] = ipc["target_period_start"] - pd.Timedelta(days=30)
    ipc = ipc.sort_values(["region_id", "target_period_start"])

    region_rain = rain.groupby(["region_id", "date"], as_index=False).agg(
        rainfall_mean_mm=("rainfall_mean_mm", "mean"), dry_fraction=("rainfall_mean_mm", lambda values: float((values < 1.0).mean()))
    ).sort_values(["region_id", "date"])
    for window in (30, 90):
        region_rain[f"rain_{window}d_mm"] = region_rain.groupby("region_id", sort=False)["rainfall_mean_mm"].transform(
            lambda values, w=window: values.rolling(w, min_periods=w).sum()
        )
    region_rain["dry_days_30d"] = region_rain.groupby("region_id", sort=False)["dry_fraction"].transform(
        lambda values: values.rolling(30, min_periods=30).sum()
    )
    region_power = power.groupby(["region_id", "date"], as_index=False).agg(
        t2m_c=("t2m_c", "mean"), t2m_max_c=("t2m_max_c", "mean"),
        gwet_top_relative=("gwet_top_relative", "mean"), gwet_root_relative=("gwet_root_relative", "mean")
    ).sort_values(["region_id", "date"])
    for source, output in [
        ("t2m_c", "t2m_30d_c"), ("t2m_max_c", "t2m_max_30d_c"),
        ("gwet_top_relative", "gwet_top_30d"), ("gwet_root_relative", "gwet_root_30d"),
    ]:
        region_power[output] = region_power.groupby("region_id", sort=False)[source].transform(
            lambda values: values.rolling(30, min_periods=30).mean()
        )
    vegetation = pd.read_csv(DATA / "processed" / "vegetation" / "mod13q1_v061_district_2015-01-01_2025-12-31.csv")
    vegetation["date"] = pd.to_datetime(vegetation["date"])
    vegetation = vegetation.groupby(["region_id", "date"], as_index=False).agg(
        ndvi_last=("ndvi_mean", "mean"), vegetation_valid_pixel_fraction=("valid_pixel_fraction", "mean")
    ).sort_values(["region_id", "date"])
    vegetation["vegetation_feature_timestamp"] = vegetation["date"] + pd.Timedelta(days=15)
    vegetation["ndvi_change"] = vegetation.groupby("region_id")["ndvi_last"].diff()

    market = pd.read_csv(DATA / "processed" / "market_prices" / "wfp_food_prices_canonical.csv")
    market["date"] = pd.to_datetime(market["date"])
    market = market[
        market["canonical_region_id"].notna() & market["unit"].eq("KG")
        & market["pricetype"].str.casefold().eq("retail")
        & market["category"].str.contains("cereals", case=False, na=False)
        & (pd.to_numeric(market["usdprice"], errors="coerce") > 0)
    ].copy()
    market["usdprice"] = pd.to_numeric(market["usdprice"], errors="coerce")
    population = pd.read_csv(DATA / "processed" / "population" / "region_population_2025.csv")
    population_map = dict(zip(population["canonical_region_id"], population["region_population"]))

    rows = []
    for _, target in ipc.iterrows():
        region_id = target["region_id"]
        as_of = target["feature_as_of_date"]
        rain_row = region_rain[(region_rain["region_id"] == region_id) & (region_rain["date"] == as_of)]
        power_row = region_power[(region_power["region_id"] == region_id) & (region_power["date"] == as_of)]
        veg_rows = vegetation[(vegetation["region_id"] == region_id) & (vegetation["vegetation_feature_timestamp"] <= as_of)]
        veg_row = veg_rows.iloc[-1] if len(veg_rows) else None
        prices = market[(market["canonical_region_id"] == region_id) & (market["date"] <= as_of)]
        recent = prices[prices["date"] > as_of - pd.Timedelta(days=90)]
        prior = prices[(prices["date"] <= as_of - pd.Timedelta(days=90)) & (prices["date"] > as_of - pd.Timedelta(days=180))]
        annual = prices[prices["date"] > as_of - pd.Timedelta(days=365)]
        recent_price = float(recent["usdprice"].median()) if len(recent) else np.nan
        prior_price = float(prior["usdprice"].median()) if len(prior) else np.nan
        annual_price = float(annual["usdprice"].median()) if len(annual) else np.nan
        previous = ipc[
            (ipc["region_id"] == region_id)
            & (ipc["target_period_end"] <= as_of)
            & (ipc["target_period_start"] < target["target_period_start"])
        ].sort_values("target_period_end")
        previous_row = previous.iloc[-1] if len(previous) else None
        row = target.to_dict()
        row.update(
            {
                "rain_30d_mm": rain_row["rain_30d_mm"].iloc[0] if len(rain_row) else np.nan,
                "rain_90d_mm": rain_row["rain_90d_mm"].iloc[0] if len(rain_row) else np.nan,
                "dry_days_30d": rain_row["dry_days_30d"].iloc[0] if len(rain_row) else np.nan,
                "t2m_30d_c": power_row["t2m_30d_c"].iloc[0] if len(power_row) else np.nan,
                "t2m_max_30d_c": power_row["t2m_max_30d_c"].iloc[0] if len(power_row) else np.nan,
                "gwet_top_30d": power_row["gwet_top_30d"].iloc[0] if len(power_row) else np.nan,
                "gwet_root_30d": power_row["gwet_root_30d"].iloc[0] if len(power_row) else np.nan,
                "ndvi_last": veg_row["ndvi_last"] if veg_row is not None else np.nan,
                "ndvi_change": veg_row["ndvi_change"] if veg_row is not None else np.nan,
                "vegetation_valid_pixel_fraction": veg_row["vegetation_valid_pixel_fraction"] if veg_row is not None else np.nan,
                "market_usdkg_90d_median": recent_price,
                "market_price_change_previous_90d": recent_price / prior_price - 1 if prior_price and np.isfinite(prior_price) else np.nan,
                "market_price_anomaly_365d": recent_price / annual_price - 1 if annual_price and np.isfinite(annual_price) else np.nan,
                "previous_ipc3plus_percentage": previous_row["target_ipc3plus_percentage"] if previous_row is not None else np.nan,
                "log_region_population": np.log1p(population_map.get(region_id, np.nan)),
                "rainfall_feature_timestamp": as_of if len(rain_row) else pd.NaT,
                "power_feature_timestamp": as_of if len(power_row) else pd.NaT,
                "vegetation_feature_timestamp": veg_row["vegetation_feature_timestamp"] if veg_row is not None else pd.NaT,
                "market_feature_timestamp": prices["date"].max() if len(prices) else pd.NaT,
                "previous_ipc_feature_timestamp": previous_row["target_period_end"] if previous_row is not None else pd.NaT,
                "market_observations_90d": len(recent),
            }
        )
        rows.append(row)
    frame = pd.DataFrame(rows)
    keep = [
        "region_id", "region_name_source", "feature_as_of_date", "target_period_start",
        "target_period_end", "target", "target_ipc3plus_percentage", "rainfall_feature_timestamp",
        "power_feature_timestamp", "vegetation_feature_timestamp", "market_feature_timestamp",
        "previous_ipc_feature_timestamp", "market_observations_90d", *FEATURES["food_security"],
    ]
    frame = frame[keep].sort_values(["target_period_start", "region_id"]).reset_index(drop=True)
    return frame, {"unresolved_target_rows": unresolved, "ipc_projection_rows_excluded": int((ipc["assessment_period_type"] != "current").sum()) if "assessment_period_type" in ipc else None}


def dataset_metadata(track: str, frame: pd.DataFrame, path: Path, notes: dict[str, Any]) -> dict[str, Any]:
    target_date = "target_period_start"
    missing = {feature: float(frame[feature].isna().mean()) for feature in FEATURES[track]}
    return finite_or_none(
        {
            "track": track,
            "dataset_version": RUN_VERSION,
            "created_at": now(),
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
            "rows": len(frame),
            "features": FEATURES[track],
            "feature_count": len(FEATURES[track]),
            "target_definition": TARGETS[track],
            "temporal_coverage": {
                "start": frame[target_date].min().date().isoformat(),
                "end": frame[target_date].max().date().isoformat(),
            },
            "geographic_coverage": {
                key: int(frame[key].nunique())
                for key in ("district_id", "region_id", "station_code") if key in frame
            },
            "target_counts": {
                "positive": int(frame["target"].sum()),
                "negative": int((1 - frame["target"]).sum()),
                "positive_rate": float(frame["target"].mean()),
            },
            "feature_missing_fraction": missing,
            "maximum_feature_missing_fraction": max(missing.values()),
            "source_lineage": [
                "data/metadata/historical_archive_manifest.csv",
                "data/metadata/nasa_power_history_manifest.json",
                "data/metadata/source_registry.json",
                "data/metadata/geographic_crosswalk.csv",
            ],
            "notes": notes,
        }
    )


def build_datasets() -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    started = time.perf_counter()
    rain, power = _climate_daily()
    builders = {
        "drought": lambda: build_drought_dataset(rain, power),
        "flood": lambda: build_flood_dataset(rain, power),
        "food_security": lambda: build_food_dataset(rain, power),
    }
    datasets: dict[str, pd.DataFrame] = {}
    metadata: dict[str, Any] = {}
    target_summary: dict[str, Any] = {"generated_at": now(), "target_version": TARGETS["version"], "tracks": {}}
    for track, builder in builders.items():
        frame, notes = builder()
        path = MODEL_READY / track / f"{track}_dataset_v{RUN_VERSION}.csv.gz"
        write_csv(path, frame)
        item = dataset_metadata(track, frame, path, notes)
        write_json(MODEL_READY / track / f"metadata_v{RUN_VERSION}.json", item)
        write_json(MODEL_READY / track / f"feature_schema_v{RUN_VERSION}.json", {
            "version": RUN_VERSION, "track": track, "features": [{"name": f, "dtype": "float64", "required": f in FEATURES[track][:3]} for f in FEATURES[track]]
        })
        distribution = frame.assign(year=pd.to_datetime(frame["target_period_start"]).dt.year).groupby("year")["target"].agg(["count", "sum", "mean"]).reset_index().to_dict("records")
        geography_key = next((key for key in ("district_id", "station_code", "region_id") if key in frame), None)
        geographic = frame.groupby(geography_key)["target"].agg(["count", "sum", "mean"]).reset_index().to_dict("records") if geography_key else []
        target_summary["tracks"][track] = finite_or_none({
            "positive_count": int(frame.target.sum()), "negative_count": int((1-frame.target).sum()),
            "unknown_count": notes.get("label_unknown_rows", notes.get("unknown_future_windows", notes.get("unresolved_target_rows", 0))),
            "positive_rate": frame.target.mean(), "temporal_distribution": distribution,
            "geographic_distribution": geographic, "longest_gap_days": int(pd.to_datetime(frame.target_period_start).sort_values().drop_duplicates().diff().dt.days.max()),
        })
        datasets[track] = frame
        metadata[track] = item
    target_summary["build_seconds"] = time.perf_counter() - started
    write_json(METADATA / "phase02_target_summary.json", target_summary)
    return datasets, metadata


def partition(frame: pd.DataFrame, track: str) -> dict[str, pd.DataFrame]:
    year = pd.to_datetime(frame["target_period_start"]).dt.year
    result = {}
    for name, (start, end) in SPLITS[track].items():
        result[name] = frame[year.between(start, end)].copy().reset_index(drop=True)
    return result


def make_model(name: str, track: str) -> Any:
    if name == "rule":
        return RuleEstimator(track)
    imputer = SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)
    if name == "logistic_regression":
        return Pipeline([
            ("imputer", imputer), ("scale", StandardScaler()),
            ("model", LogisticRegression(max_iter=2000, class_weight="balanced", C=1.0, random_state=RANDOM_SEED)),
        ])
    return Pipeline([
        ("imputer", imputer),
        ("model", RandomForestClassifier(
            n_estimators=250, max_depth=8, min_samples_leaf=10 if track != "food_security" else 5,
            max_features="sqrt", class_weight="balanced_subsample", random_state=RANDOM_SEED,
            n_jobs=-1,
        )),
    ])


def selection_utility(result: dict[str, Any]) -> float:
    return float(0.35 * (result.get("pr_auc") or 0) + 0.25 * (result.get("recall") or 0) + 0.20 * (result.get("f1") or 0) + 0.20 * (1 - (result.get("brier") or 1)))


def evaluate_track(track: str, frame: pd.DataFrame) -> dict[str, Any]:
    started = time.perf_counter()
    parts = partition(frame, track)
    features = FEATURES[track]
    minimum_recall = ACCEPTANCE[track]["minimum_test_recall"]
    maximum_far = ACCEPTANCE[track]["maximum_false_alarm_rate"]
    prevalence = float(parts["train"]["target"].mean())
    rule_model = make_model("rule", track)
    rule_model.fit(parts["train"][features], parts["train"]["target"])
    baseline_val_probability = rule_model.predict_proba(parts["validation"][features])[:, 1]
    baseline_threshold, baseline_val = choose_threshold(
        parts["validation"].target.to_numpy(), baseline_val_probability, minimum_recall, maximum_far
    )
    baseline_test_probability = rule_model.predict_proba(parts["test"][features])[:, 1]
    baseline_test = metrics(parts["test"].target.to_numpy(), baseline_test_probability, baseline_threshold)
    candidates: dict[str, Any] = {}
    fitted: dict[str, Any] = {"rule": rule_model}
    for name in ("logistic_regression", "random_forest"):
        before = time.perf_counter()
        model = make_model(name, track)
        model.fit(parts["train"][features], parts["train"]["target"])
        validation_probability = model.predict_proba(parts["validation"][features])[:, 1]
        threshold, validation_metrics = choose_threshold(
            parts["validation"].target.to_numpy(), validation_probability, minimum_recall, maximum_far
        )
        candidates[name] = {
            "algorithm": name, "parameters": model.named_steps["model"].get_params(deep=False),
            "validation_metrics": validation_metrics, "validation_utility": selection_utility(validation_metrics),
            "training_seconds": time.perf_counter() - before, "threshold_before_calibration": threshold,
        }
        fitted[name] = model
    rule_utility = selection_utility(baseline_val)
    logistic_utility = candidates["logistic_regression"]["validation_utility"]
    forest_utility = candidates["random_forest"]["validation_utility"]
    baseline_name = "logistic_regression" if logistic_utility >= rule_utility + 0.02 else "rule"
    baseline_utility = logistic_utility if baseline_name == "logistic_regression" else rule_utility
    selected_name = "random_forest" if forest_utility >= baseline_utility + 0.02 else baseline_name
    if selected_name == "random_forest":
        selection_reason = "Random forest exceeded the best baseline by the predeclared 0.02 validation-utility margin."
    elif selected_name == "logistic_regression":
        selection_reason = "Logistic regression improved on the deterministic rule, while random forest added less than 0.02 validation utility."
    else:
        selection_reason = "Neither statistical nor advanced ML improved validation utility by 0.02; the deterministic operational baseline was retained."
    selected = fitted[selected_name]
    validation_raw = selected.predict_proba(parts["validation"][features])[:, 1]
    calibrator, calibration = fit_calibrator(
        parts["validation"].target.to_numpy(), validation_raw, reference_prevalence=prevalence
    )
    validation_probability = calibrator.predict(validation_raw)
    threshold, calibrated_validation_metrics = choose_threshold(
        parts["validation"].target.to_numpy(), validation_probability, minimum_recall, maximum_far
    )
    test_raw = selected.predict_proba(parts["test"][features])[:, 1]
    test_probability = calibrator.predict(test_raw)
    final_test_metrics = metrics(parts["test"].target.to_numpy(), test_probability, threshold)
    raw_test_metrics = metrics(parts["test"].target.to_numpy(), test_raw, threshold)
    calibration.update({
        "test_brier_before": raw_test_metrics["brier"], "test_brier_after": final_test_metrics["brier"],
        "test_ece_before": raw_test_metrics["ece_10_bin"], "test_ece_after": final_test_metrics["ece_10_bin"],
    })
    medians = {feature: float(pd.to_numeric(parts["train"][feature], errors="coerce").median()) for feature in features}
    ranges = {
        feature: (
            float(pd.to_numeric(parts["train"][feature], errors="coerce").quantile(0.01)),
            float(pd.to_numeric(parts["train"][feature], errors="coerce").quantile(0.99)),
        )
        for feature in features
    }
    risk_thresholds = {
        "watch": max(0.01, threshold * 0.5), "warning": threshold,
        "severe": min(0.99, threshold + 0.5 * (1 - threshold)),
    }
    bundle = ModelBundle(
        track=track, version=f"{track}-{RUN_VERSION}", feature_names=features, estimator=selected,
        calibrator=calibrator, operating_threshold=threshold, risk_thresholds=risk_thresholds,
        critical_features=features[:3], training_medians=medians, training_ranges=ranges,
    )
    artifact_dir = ARTIFACTS / track
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{track}_model_v{RUN_VERSION}.joblib"
    joblib.dump(bundle, artifact_path)
    loaded: ModelBundle = joblib.load(artifact_path)
    round_trip_probability = loaded.predict_probability(parts["test"].head(20))
    serialization_passed = bool(np.allclose(round_trip_probability, test_probability[:20]))
    explanation = global_and_local_explanations(
        bundle, parts["train"], parts["test"], parts["test"].target.to_numpy(),
        [key for key in ("district_id", "station_code", "region_id", "feature_as_of_date", "target_period_start") if key in frame],
    )
    write_json(artifact_dir / "explainability.json", finite_or_none(explanation))
    drift = {
        feature: {
            "psi_train_to_validation": population_stability_index(parts["train"][feature], parts["validation"][feature]),
            "psi_train_to_test": population_stability_index(parts["train"][feature], parts["test"][feature]),
        }
        for feature in features
    }
    write_json(artifact_dir / "feature_drift.json", finite_or_none(drift))
    predictions = parts["test"][[key for key in ("district_id", "station_code", "region_id", "feature_as_of_date", "target_period_start", "target_period_end", "target", "target_first_crossing_lead_days") if key in parts["test"]]].copy()
    predictions["probability"] = test_probability
    predictions["prediction"] = (test_probability >= threshold).astype(int)
    predictions["correct"] = predictions["prediction"] == predictions["target"]
    write_csv(artifact_dir / "historical_replay.csv.gz", predictions)
    false_positive = predictions[(predictions.target == 0) & (predictions.prediction == 1)].sort_values("probability", ascending=False).head(25)
    false_negative = predictions[(predictions.target == 1) & (predictions.prediction == 0)].sort_values("probability").head(25)
    failure_analysis = {
        "false_positive_count": int(((predictions.target == 0) & (predictions.prediction == 1)).sum()),
        "false_negative_count": int(((predictions.target == 1) & (predictions.prediction == 0)).sum()),
        "highest_confidence_false_positives": finite_or_none(false_positive.to_dict("records")),
        "highest_confidence_false_negatives": finite_or_none(false_negative.to_dict("records")),
    }
    if "station_code" in predictions:
        failure_analysis["errors_by_station"] = predictions[~predictions.correct].groupby("station_code").size().to_dict()
    if "region_id" in predictions:
        failure_analysis["errors_by_region"] = predictions[~predictions.correct].groupby("region_id").size().to_dict()
    write_json(artifact_dir / "failure_analysis.json", failure_analysis)
    candidate_test = {}
    for name in ("logistic_regression", "random_forest"):
        model = fitted[name]
        probability = model.predict_proba(parts["test"][features])[:, 1]
        candidate_test[name] = metrics(parts["test"].target.to_numpy(), probability, candidates[name]["threshold_before_calibration"])
    baseline_metrics = {"rule": {"validation": baseline_val, "test": baseline_test}, "logistic_regression": {"validation": candidates["logistic_regression"]["validation_metrics"], "test": candidate_test["logistic_regression"]}}
    write_json(artifact_dir / "baseline_metrics.json", finite_or_none(baseline_metrics))
    write_json(artifact_dir / "candidate_metrics.json", finite_or_none({name: {**details, "test_metrics_frozen_evaluation": candidate_test[name]} for name, details in candidates.items()}))
    write_json(artifact_dir / "calibration.json", finite_or_none(calibration))
    write_json(artifact_dir / "thresholds.json", {"version": RUN_VERSION, **risk_thresholds, "selection_data": "validation only"})
    artifact_metadata = {
        "model_id": f"{track}-early-warning", "model_version": RUN_VERSION, "target_version": TARGETS["version"],
        "feature_version": RUN_VERSION, "algorithm": selected_name, "features": features,
        "training_period": SPLITS[track]["train"], "validation_period": SPLITS[track]["validation"],
        "test_period": SPLITS[track]["test"], "calibration_method": calibrator.method,
        "operating_threshold": threshold, "risk_thresholds": risk_thresholds,
        "artifact_path": str(artifact_path.relative_to(ROOT)).replace("\\", "/"),
        "artifact_checksum_sha256": sha256(artifact_path), "artifact_size_bytes": artifact_path.stat().st_size,
        "serialization_round_trip_passed": serialization_passed, "environment": environment_metadata(),
        "selection_reason": selection_reason,
    }
    write_json(artifact_dir / "model_metadata.json", finite_or_none(artifact_metadata))
    write_json(artifact_dir / "inference_contract.json", {
        "version": RUN_VERSION, "input": {"identity": "district_id, station_code, or region_id", "as_of_date": "ISO-8601 date", "features": features},
        "output": ["model_version", "risk_type", "probability", "risk_level", "prediction_horizon", "top_drivers", "data_quality", "generated_at"],
        "data_quality": {"GOOD": "all critical features present and within training guardrails", "DEGRADED": "some optional data absent or outside 1st-99th percentile", "INSUFFICIENT": "less than half of critical features present; probability withheld"},
    })
    result = {
        "track": track, "selected_model": selected_name, "selection_reason": selection_reason,
        "partitions": {name: {"rows": len(value), "positive": int(value.target.sum()), "negative": int((1-value.target).sum()), "start": value.target_period_start.min().date().isoformat(), "end": value.target_period_start.max().date().isoformat()} for name, value in parts.items()},
        "baseline": baseline_metrics, "candidates": candidates, "candidate_test_metrics": candidate_test,
        "calibration": calibration, "operating_threshold": threshold, "risk_thresholds": risk_thresholds,
        "validation_metrics_after_calibration": calibrated_validation_metrics, "final_test_metrics": final_test_metrics,
        "artifact": artifact_metadata, "explainability": {"available": True, "method": explanation["method"], "shap_status": explanation["shap_status"], "top_features": explanation["global_feature_importance"][:10]},
        "drift": drift, "failure_analysis": failure_analysis, "training_and_evaluation_seconds": time.perf_counter() - started,
    }
    if track == "flood":
        station_results = {}
        for station_code, group in predictions.groupby("station_code"):
            station_results[station_code] = metrics(group.target.to_numpy(), group.probability.to_numpy(), threshold)
        result["station_test_metrics"] = station_results
    return finite_or_none(result)


def rolling_backtest(track: str, frame: pd.DataFrame, algorithm: str) -> dict[str, Any]:
    features = FEATURES[track]
    years = sorted(pd.to_datetime(frame.target_period_start).dt.year.unique())
    first_year = 2021 if track in {"drought", "food_security"} else 2019
    folds = []
    all_predictions = []
    for test_year in [year for year in years if year >= first_year and year <= 2025]:
        validation_year = test_year - 1
        date_year = pd.to_datetime(frame.target_period_start).dt.year
        train = frame[date_year < validation_year]
        validation = frame[date_year == validation_year]
        test = frame[date_year == test_year]
        if min(len(train), len(validation), len(test)) == 0 or train.target.nunique() < 2 or validation.target.nunique() < 2 or test.target.nunique() < 2:
            continue
        model = make_model(algorithm, track)
        model.fit(train[features], train.target)
        validation_raw = model.predict_proba(validation[features])[:, 1]
        calibrator, calibration = fit_calibrator(
            validation.target.to_numpy(), validation_raw, reference_prevalence=float(train.target.mean())
        )
        validation_probability = calibrator.predict(validation_raw)
        threshold, _ = choose_threshold(
            validation.target.to_numpy(), validation_probability,
            ACCEPTANCE[track]["minimum_test_recall"], ACCEPTANCE[track]["maximum_false_alarm_rate"]
        )
        probability = calibrator.predict(model.predict_proba(test[features])[:, 1])
        fold_metrics = metrics(test.target.to_numpy(), probability, threshold)
        folds.append({"train_end_year": validation_year - 1, "validation_year": validation_year, "test_year": test_year, "metrics": fold_metrics, "calibration_method": calibration["method"]})
        keys = [key for key in ("district_id", "station_code", "region_id", "feature_as_of_date", "target_period_start", "target", "target_first_crossing_lead_days") if key in test]
        fold_predictions = test[keys].copy()
        fold_predictions["probability"] = probability
        fold_predictions["prediction"] = (probability >= threshold).astype(int)
        fold_predictions["fold_test_year"] = test_year
        all_predictions.append(fold_predictions)
    predictions = pd.concat(all_predictions, ignore_index=True) if all_predictions else pd.DataFrame()
    path = ARTIFACTS / track / "rolling_backtest_predictions.csv.gz"
    write_csv(path, predictions)
    summary = {
        "method": "expanding window; prior year used for calibration/threshold; next year held out",
        "fold_count": len(folds), "folds": folds,
        "prediction_rows": len(predictions), "predictions_path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "predictions_sha256": sha256(path),
    }
    if len(predictions):
        # Ranking/calibration metrics use the pooled probabilities. Operational
        # classification metrics must use each fold's validation-only threshold,
        # not an unrelated pooled 0.50 threshold.
        y_true = predictions.target.to_numpy(dtype=int)
        y_pred = predictions.prediction.to_numpy(dtype=int)
        overall = metrics(y_true, predictions.probability.to_numpy(), 0.5)
        tn = int(((y_true == 0) & (y_pred == 0)).sum())
        fp = int(((y_true == 0) & (y_pred == 1)).sum())
        fn = int(((y_true == 1) & (y_pred == 0)).sum())
        tp = int(((y_true == 1) & (y_pred == 1)).sum())
        recall = tp / (tp + fn) if tp + fn else 0.0
        specificity = tn / (tn + fp) if tn + fp else 0.0
        precision = tp / (tp + fp) if tp + fp else 0.0
        overall.update({
            "threshold": "fold_specific_validation_thresholds",
            "accuracy": (tp + tn) / len(y_true),
            "balanced_accuracy": (recall + specificity) / 2.0,
            "precision": precision,
            "recall": recall,
            "f1": 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0,
            "false_alarm_rate": fp / (fp + tn) if fp + tn else 0.0,
            "miss_rate": fn / (fn + tp) if fn + tp else 0.0,
            "true_negative": tn, "false_positive": fp,
            "false_negative": fn, "true_positive": tp,
        })
        summary["overall_metrics"] = overall
        true_positive = predictions[(predictions.target == 1) & (predictions.prediction == 1)]
        if track == "flood" and "target_first_crossing_lead_days" in true_positive:
            summary["mean_detected_lead_time_days"] = float(true_positive.target_first_crossing_lead_days.mean())
        else:
            summary["mean_detected_lead_time_days"] = 16.0 if track == "drought" else 30.0
    write_json(ARTIFACTS / track / "backtest_summary.json", finite_or_none(summary))
    return finite_or_none(summary)


def track_leakage_checks(track: str, frame: pd.DataFrame) -> dict[str, bool]:
    """Return independently testable temporal, key, and feature leakage checks."""
    timestamp_columns = {
        "drought": ["vegetation_feature_timestamp", "rainfall_feature_timestamp", "power_feature_timestamp"],
        "flood": ["river_feature_timestamp", "rainfall_feature_timestamp", "power_feature_timestamp"],
        "food_security": ["rainfall_feature_timestamp", "power_feature_timestamp", "vegetation_feature_timestamp", "market_feature_timestamp", "previous_ipc_feature_timestamp"],
    }
    duplicate_keys = {
        "drought": ["district_id", "feature_as_of_date", "target_period_start"],
        "flood": ["station_code", "feature_as_of_date"],
        "food_security": ["region_id", "target_period_start"],
    }
    checks = {}
    as_of = pd.to_datetime(frame.feature_as_of_date)
    for column in timestamp_columns[track]:
        timestamp = pd.to_datetime(frame[column], errors="coerce")
        checks[f"{column}_not_future"] = bool((timestamp.dropna() <= as_of[timestamp.notna()]).all())
    checks["target_after_as_of"] = bool((pd.to_datetime(frame.target_period_start) > as_of).all())
    checks["unique_observation_keys"] = not frame.duplicated(duplicate_keys[track]).any()
    checks["no_target_columns_in_features"] = not any(feature.startswith("target") or "future" in feature for feature in FEATURES[track])
    parts = partition(frame, track)
    checks["split_time_order"] = bool(
        pd.to_datetime(parts["train"].target_period_start).max() < pd.to_datetime(parts["validation"].target_period_start).min()
        and pd.to_datetime(parts["validation"].target_period_start).max() < pd.to_datetime(parts["test"].target_period_start).min()
    )
    return checks


def leakage_audit(datasets: dict[str, pd.DataFrame]) -> dict[str, Any]:
    report = {"generated_at": now(), "status": "PASS", "tracks": {}}
    for track, frame in datasets.items():
        checks = track_leakage_checks(track, frame)
        report["tracks"][track] = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
    if any(item["status"] != "PASS" for item in report["tracks"].values()):
        report["status"] = "FAIL"
    write_json(METADATA / "phase02_leakage_report.json", report)
    return report


def git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def run_phase02() -> dict[str, Any]:
    run_started = time.perf_counter()
    datasets, dataset_info = build_datasets()
    leakage = leakage_audit(datasets)
    if leakage["status"] != "PASS":
        raise RuntimeError("Phase 02 leakage audit failed; training is blocked")
    model_results = {track: evaluate_track(track, frame) for track, frame in datasets.items()}
    backtests = {track: rolling_backtest(track, datasets[track], model_results[track]["selected_model"]) for track in datasets}
    experiment_rows = []
    metric_rows = []
    for track, result in model_results.items():
        dataset_meta = dataset_info[track]
        experiment_rows.append({
            "experiment_id": f"{track}-rule-v1", "timestamp": now(), "dataset_version": dataset_meta["dataset_version"],
            "dataset_checksum": dataset_meta["sha256"], "feature_version": RUN_VERSION, "target_version": TARGETS["version"],
            "algorithm": "rule", "parameters": json.dumps({"type": "deterministic domain baseline"}),
            "metrics": json.dumps(result["baseline"]["rule"]["validation"], sort_keys=True),
            "status": "selected" if result["selected_model"] == "rule" else "evaluated", "notes": result["selection_reason"],
        })
        for name, candidate in result["candidates"].items():
            experiment_rows.append({
                "experiment_id": f"{track}-{name}-v1", "timestamp": now(), "dataset_version": dataset_meta["dataset_version"],
                "dataset_checksum": dataset_meta["sha256"], "feature_version": RUN_VERSION, "target_version": TARGETS["version"],
                "algorithm": name, "parameters": json.dumps(candidate["parameters"], default=str, sort_keys=True),
                "metrics": json.dumps(candidate["validation_metrics"], sort_keys=True),
                "status": "selected" if name == result["selected_model"] else "evaluated", "notes": result["selection_reason"],
            })
        final = result["final_test_metrics"]
        artifact = result["artifact"]
        metric_rows.append({
            "model_id": artifact["model_id"], "model_version": artifact["model_version"], "target": TARGETS[track]["target_name"],
            "algorithm": result["selected_model"], "training_period": f"{SPLITS[track]['train'][0]}-{SPLITS[track]['train'][1]}",
            "validation_period": f"{SPLITS[track]['validation'][0]}-{SPLITS[track]['validation'][1]}",
            "test_period": f"{SPLITS[track]['test'][0]}-{SPLITS[track]['test'][1]}", "features": json.dumps(FEATURES[track]),
            "precision": final["precision"], "recall": final["recall"], "f1": final["f1"], "roc_auc": final["roc_auc"],
            "pr_auc": final["pr_auc"], "brier": final["brier"], "false_alarm_rate": final["false_alarm_rate"],
            "miss_rate": final["miss_rate"], "lead_time_days": backtests[track].get("mean_detected_lead_time_days"),
            "calibration_method": result["calibration"]["method"], "operating_threshold": result["operating_threshold"],
            "artifact_path": artifact["artifact_path"], "checksum": artifact["artifact_checksum_sha256"],
        })
    experiments = pd.DataFrame(experiment_rows)
    metrics_registry = pd.DataFrame(metric_rows)
    write_csv(REPORTS / "experiment_registry.csv", experiments)
    write_json(REPORTS / "experiment_registry.json", finite_or_none(experiment_rows))
    write_csv(REPORTS / "model_metrics_registry.csv", metrics_registry)
    write_json(REPORTS / "model_metrics_registry.json", finite_or_none(metric_rows))
    summary = {
        "generated_at": now(), "phase02_version": RUN_VERSION, "git_commit": git_commit(),
        "environment": environment_metadata(), "dataset_build": dataset_info, "leakage": leakage,
        "models": model_results, "backtesting": backtests, "run_seconds": time.perf_counter() - run_started,
    }
    write_json(REPORTS / "phase02_run_summary.json", finite_or_none(summary))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the complete reproducible Phase 02 modeling workflow")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "build"])
    args = parser.parse_args()
    if args.command == "build":
        datasets, _ = build_datasets()
        leakage = leakage_audit(datasets)
        print(json.dumps({"datasets": {key: len(value) for key, value in datasets.items()}, "leakage": leakage["status"]}, indent=2))
        return 0 if leakage["status"] == "PASS" else 1
    summary = run_phase02()
    print(json.dumps({
        "tracks": {track: {"selected_model": value["selected_model"], "test": value["final_test_metrics"]} for track, value in summary["models"].items()},
        "leakage": summary["leakage"]["status"], "backtest_folds": {track: value["fold_count"] for track, value in summary["backtesting"].items()},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
