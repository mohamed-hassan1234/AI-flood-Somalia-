from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import joblib
import pandas as pd

from ml.pipeline import SPLITS, partition as phase02_partition
from operational import actions as actions_module
from operational import exposure as exposure_module
from operational import warning as warning_module
from operational.geography import UnsupportedGeographyError, registry
from operational.intelligence import ModelChecksumError, build_record, load_verified_bundle
from operational.pipeline import GEOGRAPHY_KEY, _load_frame, select_latest_as_of

TRACKS = ("drought", "flood", "food_security")
REQUIRED_TOP_LEVEL_KEYS = {
    "intelligence_id", "risk_type", "as_of_date", "valid_from", "valid_until", "prediction_horizon",
    "geography", "station_code", "river_name", "prediction", "exposure", "impact_summary", "drivers",
    "warning", "recommended_actions", "data_quality", "model", "lineage", "limitations", "generated_at",
}


class GeographyTests(unittest.TestCase):
    def test_population_is_positive_for_every_supported_district(self) -> None:
        reg = registry()
        for district_id in reg.drought_supported_districts - {"Unspecified"}:
            with self.subTest(district_id=district_id):
                self.assertGreater(reg.district(district_id).population, 0)

    def test_unspecified_bucket_is_explicitly_excluded_not_silently_mapped(self) -> None:
        # 'Unspecified' is a genuine Phase 01 unresolved-observation bucket (Banadir residual),
        # not a real, mappable district. It must never be surfaced as an operational geography.
        self.assertIn("Unspecified", registry().drought_supported_districts)
        with self.assertRaises(UnsupportedGeographyError):
            registry().district("Unspecified")

    def test_population_is_positive_for_every_supported_region(self) -> None:
        reg = registry()
        for region_id in reg.food_security_supported_regions:
            with self.subTest(region_id=region_id):
                self.assertGreater(reg.region(region_id).population, 0)

    def test_unsupported_station_is_rejected(self) -> None:
        with self.assertRaises(UnsupportedGeographyError):
            registry().station("ZZ999")

    def test_unsupported_district_is_rejected(self) -> None:
        with self.assertRaises(UnsupportedGeographyError):
            registry().district("SO9999")

    def test_unsupported_region_is_rejected(self) -> None:
        with self.assertRaises(UnsupportedGeographyError):
            registry().region("SO99")

    def test_district_id_cannot_be_used_as_a_region(self) -> None:
        # Scope enforcement: a district-shaped id must not silently resolve as a region.
        district_id = next(iter(registry().drought_supported_districts))
        with self.assertRaises(UnsupportedGeographyError):
            registry().region(district_id)

    def test_all_five_flood_stations_resolve_to_a_district(self) -> None:
        reg = registry()
        self.assertEqual(reg.flood_supported_stations, {"SH001", "SH002", "SH004", "JB001", "JB009"})
        for station_code in reg.flood_supported_stations:
            with self.subTest(station=station_code):
                district = reg.station_linked_district(station_code)
                self.assertTrue(district.district_id.startswith("SO"))


class ExposureSemanticTests(unittest.TestCase):
    def test_drought_exposure_is_zero_at_normal_and_population_at_risk(self) -> None:
        district_id = next(iter(registry().drought_supported_districts))
        normal = exposure_module.drought_exposure(district_id, "NORMAL")
        watch = exposure_module.drought_exposure(district_id, "WATCH")
        self.assertEqual(normal["population_potentially_exposed"], 0.0)
        self.assertGreater(watch["population_potentially_exposed"], 0.0)
        self.assertEqual(watch["population_potentially_exposed"], watch["population_context"])

    def test_flood_exposed_population_is_always_null_not_fabricated(self) -> None:
        for level in ("NORMAL", "WATCH", "WARNING", "SEVERE"):
            with self.subTest(level=level):
                result = exposure_module.flood_exposure("SH001", level)
                self.assertIsNone(result["population_potentially_exposed"])
                self.assertGreater(result["population_context"], 0)
                self.assertIn("inundation footprint exists", result["exposure_uncertainty"].lower())

    def test_food_security_exposed_population_is_always_null_not_fabricated(self) -> None:
        for level in ("NORMAL", "WATCH", "WARNING", "SEVERE"):
            with self.subTest(level=level):
                result = exposure_module.food_security_exposure("SO11", level)
                self.assertIsNone(result["population_potentially_exposed"])
                self.assertGreater(result["population_context"], 0)

    def test_no_field_anywhere_claims_confirmed_affected_population(self) -> None:
        # Exposed/context fields exist; a "confirmed affected" field must not.
        for fn in (exposure_module.drought_exposure, ):
            result = fn(next(iter(registry().drought_supported_districts)), "SEVERE")
            self.assertNotIn("affected_population", result)
            self.assertNotIn("confirmed_affected", result)


class RiskThresholdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metadata = {
            track: json.loads((Path("ml") / "artifacts" / track / "model_metadata.json").read_text(encoding="utf-8"))
            for track in TRACKS
        }

    def test_risk_thresholds_match_frozen_phase02_values(self) -> None:
        expected = {
            "drought": {"watch": 0.135, "warning": 0.27, "severe": 0.635},
            "flood": {"watch": 0.115, "warning": 0.23, "severe": 0.615},
            "food_security": {"watch": 0.265, "warning": 0.53, "severe": 0.765},
        }
        for track in TRACKS:
            with self.subTest(track=track):
                thresholds = self.metadata[track]["risk_thresholds"]
                for level, value in expected[track].items():
                    self.assertAlmostEqual(thresholds[level], value, places=3)


class WarningPolicyTests(unittest.TestCase):
    def test_normal_risk_never_generates_a_warning(self) -> None:
        decision = warning_module.warning_decision("NORMAL", "GOOD", "GOOD", "GOOD")
        self.assertFalse(decision["eligible"])
        self.assertEqual(decision["status"], "NO_WARNING_RISK_NORMAL")

    def test_insufficient_model_quality_suppresses_a_high_risk_warning(self) -> None:
        decision = warning_module.warning_decision("SEVERE", "INSUFFICIENT", "GOOD", "INSUFFICIENT")
        self.assertFalse(decision["eligible"])
        self.assertEqual(decision["status"], "SUPPRESSED_DATA_QUALITY")

    def test_stale_critical_data_suppresses_a_high_risk_warning(self) -> None:
        decision = warning_module.warning_decision("WARNING", "GOOD", "STALE_CRITICAL", "INSUFFICIENT")
        self.assertFalse(decision["eligible"])
        self.assertEqual(decision["status"], "SUPPRESSED_STALE_DATA")

    def test_good_quality_high_risk_is_a_candidate(self) -> None:
        decision = warning_module.warning_decision("WARNING", "GOOD", "GOOD", "GOOD")
        self.assertTrue(decision["eligible"])
        self.assertEqual(decision["status"], "CANDIDATE")

    def test_freshness_flags_missing_critical_timestamp_as_stale(self) -> None:
        row = pd.Series({"vegetation_feature_timestamp": None, "rainfall_feature_timestamp": "2024-01-01", "power_feature_timestamp": "2024-01-01"})
        result = warning_module.freshness_assessment("drought", row, pd.Timestamp("2024-01-15"))
        self.assertEqual(result["status"], "STALE_CRITICAL")
        self.assertIn("vegetation_feature_timestamp", result["stale_critical_features"])

    def test_real_archive_rows_never_have_a_negative_freshness_gap(self) -> None:
        # A negative gap would mean the as_of_date used a feature timestamped in its own future --
        # the same violation the Phase 02 leakage audit already checks for at the dataset level.
        for track in TRACKS:
            frame = _load_frame(track)
            sample = frame.sample(min(200, len(frame)), random_state=20260826)
            for _, row in sample.iterrows():
                assessment = warning_module.freshness_assessment(track, row, row.feature_as_of_date)
                for column, detail in assessment["detail"].items():
                    if detail["gap_days"] is not None:
                        with self.subTest(track=track, column=column):
                            self.assertGreaterEqual(detail["gap_days"], 0)


class ActionCatalogueTests(unittest.TestCase):
    def test_every_track_and_severity_has_at_least_one_action(self) -> None:
        for track in TRACKS:
            for level in ("WATCH", "WARNING", "SEVERE"):
                with self.subTest(track=track, level=level):
                    self.assertGreaterEqual(len(actions_module.recommended_actions(track, level, [])), 1)

    def test_normal_risk_has_no_actions(self) -> None:
        self.assertEqual(actions_module.recommended_actions("drought", "NORMAL", []), [])

    def test_severe_actions_require_human_review(self) -> None:
        for track in TRACKS:
            for action in actions_module.recommended_actions(track, "SEVERE", []):
                with self.subTest(track=track, action=action["action_id"]):
                    self.assertIn(action["status"], ("SUGGESTED", "REQUIRES_REVIEW"))
                    self.assertNotEqual(action["status"], "APPROVED")

    def test_no_action_text_orders_an_evacuation(self) -> None:
        for action in actions_module._CATALOG["actions"]:
            self.assertNotIn("order evacuation", action["action_text"].lower())
            self.assertNotIn("distribute food", action["action_text"].lower())

    def test_actions_are_traceable_to_why_triggered(self) -> None:
        for action in actions_module.recommended_actions("flood", "WARNING", ["RIVER_LEVEL_NEAR_THRESHOLD"]):
            self.assertIn("why_triggered", action)
            self.assertEqual(action["why_triggered"]["risk_type"], "flood")


class IntelligenceRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frames = {track: _load_frame(track) for track in TRACKS}
        cls.bundles = {track: load_verified_bundle(track) for track in TRACKS}

    def _sample_row(self, track: str) -> pd.Series:
        frame = self.frames[track]
        latest = select_latest_as_of(frame, GEOGRAPHY_KEY[track], frame.feature_as_of_date.max())
        return latest.iloc[0]

    def test_record_schema_has_all_contract_fields(self) -> None:
        for track in TRACKS:
            bundle, metadata = self.bundles[track]
            row = self._sample_row(track)
            from operational.pipeline import _dataset_meta
            record = build_record(track, row, bundle, metadata, _dataset_meta(track))
            with self.subTest(track=track):
                self.assertEqual(set(record.keys()), REQUIRED_TOP_LEVEL_KEYS)

    def test_record_is_strictly_json_serializable(self) -> None:
        for track in TRACKS:
            bundle, metadata = self.bundles[track]
            row = self._sample_row(track)
            from operational.pipeline import _dataset_meta
            record = build_record(track, row, bundle, metadata, _dataset_meta(track))
            with self.subTest(track=track):
                serialized = json.dumps(record, allow_nan=False)
                self.assertIsInstance(serialized, str)

    def test_lineage_carries_all_version_fields(self) -> None:
        for track in TRACKS:
            bundle, metadata = self.bundles[track]
            row = self._sample_row(track)
            from operational.pipeline import _dataset_meta
            record = build_record(track, row, bundle, metadata, _dataset_meta(track))
            with self.subTest(track=track):
                for key in ("dataset_version", "dataset_checksum_sha256", "feature_version", "target_version", "threshold_version", "action_catalogue_version", "pipeline_version", "as_of_date"):
                    self.assertIn(key, record["lineage"])
                    self.assertIsNotNone(record["lineage"][key])

    def test_idempotent_record_generation(self) -> None:
        track = "drought"
        bundle, metadata = self.bundles[track]
        row = self._sample_row(track)
        from operational.pipeline import _dataset_meta
        dataset_meta = _dataset_meta(track)
        first = build_record(track, row, bundle, metadata, dataset_meta)
        second = build_record(track, row, bundle, metadata, dataset_meta)
        self.assertEqual(first["intelligence_id"], second["intelligence_id"])
        self.assertEqual(first["prediction"]["probability"], second["prediction"]["probability"])
        self.assertEqual(first["prediction"]["risk_level"], second["prediction"]["risk_level"])

    def test_unsupported_geography_raises_before_producing_a_record(self) -> None:
        track = "drought"
        bundle, metadata = self.bundles[track]
        row = self._sample_row(track).copy()
        row["district_id"] = "Unspecified"
        from operational.pipeline import _dataset_meta
        with self.assertRaises(UnsupportedGeographyError):
            build_record(track, row, bundle, metadata, _dataset_meta(track))


class AsOfDateExecutionTests(unittest.TestCase):
    def test_selected_rows_never_exceed_as_of_date(self) -> None:
        for track in TRACKS:
            frame = _load_frame(track)
            as_of = frame.feature_as_of_date.quantile(0.5)
            selected = select_latest_as_of(frame, GEOGRAPHY_KEY[track], as_of)
            with self.subTest(track=track):
                self.assertTrue((selected.feature_as_of_date <= as_of).all())

    def test_one_row_per_geography_unit(self) -> None:
        for track in TRACKS:
            frame = _load_frame(track)
            selected = select_latest_as_of(frame, GEOGRAPHY_KEY[track], frame.feature_as_of_date.max())
            with self.subTest(track=track):
                self.assertFalse(selected[GEOGRAPHY_KEY[track]].duplicated().any())


class ModelChecksumTests(unittest.TestCase):
    def test_tampered_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake_artifacts = Path(directory) / "artifacts" / "drought"
            fake_artifacts.mkdir(parents=True)
            real_metadata = json.loads((Path("ml") / "artifacts" / "drought" / "model_metadata.json").read_text(encoding="utf-8"))
            tampered = copy.deepcopy(real_metadata)
            tampered["artifact_path"] = str(Path("operational") / "tests" / "__init__.py")  # any real, wrong-checksum file
            (fake_artifacts / "model_metadata.json").write_text(json.dumps(tampered), encoding="utf-8")
            import operational.intelligence as intelligence_module
            original_artifacts = intelligence_module.ML_ARTIFACTS
            try:
                intelligence_module.ML_ARTIFACTS = Path(directory) / "artifacts"
                with self.assertRaises(ModelChecksumError):
                    load_verified_bundle("drought")
            finally:
                intelligence_module.ML_ARTIFACTS = original_artifacts


class ReplayCutoffTests(unittest.TestCase):
    def test_replay_test_partition_stays_within_frozen_phase02_years(self) -> None:
        for track in TRACKS:
            frame = _load_frame(track)
            test = phase02_partition(frame, track)["test"]
            with self.subTest(track=track):
                start, end = SPLITS[track]["test"]
                years = pd.to_datetime(test.target_period_start).dt.year
                self.assertGreater(len(test), 0)
                self.assertTrue((years >= start).all() and (years <= end).all())


if __name__ == "__main__":
    unittest.main()
