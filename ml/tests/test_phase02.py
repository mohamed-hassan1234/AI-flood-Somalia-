from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.common import ModelBundle, sha256
from ml.pipeline import ACCEPTANCE, FEATURES, ROOT, SPLITS, TARGETS, partition, track_leakage_checks


TRACKS = ("drought", "flood", "food_security")


class Phase02TestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frames = {
            track: pd.read_csv(
                ROOT / "data" / "model_ready" / track / f"{track}_dataset_v1.1.0.csv.gz",
                parse_dates=["feature_as_of_date", "target_period_start", "target_period_end"],
            )
            for track in TRACKS
        }
        cls.bundles: dict[str, ModelBundle] = {
            track: joblib.load(ROOT / "ml" / "artifacts" / track / f"{track}_model_v1.1.0.joblib")
            for track in TRACKS
        }

    def test_target_contract_is_frozen_and_versioned(self) -> None:
        self.assertEqual(TARGETS["version"], "1.1.0")
        self.assertTrue(TARGETS["frozen_before_final_test"])
        self.assertEqual(set(TRACKS), set(TARGETS) - {"version", "frozen_before_final_test"})

    def test_acceptance_contract_is_frozen(self) -> None:
        self.assertTrue(ACCEPTANCE["frozen_before_final_test"])

    def test_model_ready_row_minimums(self) -> None:
        for track, frame in self.frames.items():
            with self.subTest(track=track):
                self.assertGreaterEqual(len(frame), ACCEPTANCE[track]["minimum_rows"])

    def test_features_exist_and_exclude_target_fields(self) -> None:
        for track, frame in self.frames.items():
            with self.subTest(track=track):
                self.assertTrue(set(FEATURES[track]).issubset(frame.columns))
                self.assertFalse(any(name.startswith("target") or "future" in name for name in FEATURES[track]))

    def test_all_production_leakage_checks_pass(self) -> None:
        for track, frame in self.frames.items():
            with self.subTest(track=track):
                checks = track_leakage_checks(track, frame)
                self.assertTrue(all(checks.values()), checks)

    def test_future_feature_is_detected(self) -> None:
        frame = self.frames["drought"].copy()
        frame.loc[0, "vegetation_feature_timestamp"] = frame.loc[0, "feature_as_of_date"] + pd.Timedelta(days=1)
        checks = track_leakage_checks("drought", frame)
        self.assertFalse(checks["vegetation_feature_timestamp_not_future"])

    def test_duplicate_observation_is_detected(self) -> None:
        frame = pd.concat([self.frames["flood"], self.frames["flood"].iloc[[0]]], ignore_index=True)
        self.assertFalse(track_leakage_checks("flood", frame)["unique_observation_keys"])

    def test_temporal_partitions_are_disjoint_and_ordered(self) -> None:
        for track, frame in self.frames.items():
            parts = partition(frame, track)
            with self.subTest(track=track):
                self.assertLess(parts["train"].target_period_start.max(), parts["validation"].target_period_start.min())
                self.assertLess(parts["validation"].target_period_start.max(), parts["test"].target_period_start.min())
                self.assertEqual(SPLITS[track]["test"], (2023, 2025) if track != "food_security" else (2024, 2025))

    def test_drought_label_matches_frozen_definition(self) -> None:
        frame = self.frames["drought"]
        expected = (frame.target_ndvi_anomaly_z <= -1.0).astype(int)
        self.assertTrue(np.array_equal(frame.target.to_numpy(), expected.to_numpy()))
        self.assertTrue((frame.feature_as_of_date == frame.target_period_start - pd.Timedelta(days=1)).all())
        self.assertTrue((pd.to_datetime(frame.vegetation_feature_timestamp) <= frame.feature_as_of_date).all())

    def test_flood_label_matches_frozen_definition(self) -> None:
        frame = self.frames["flood"]
        expected = (frame.target_future_max_level_m >= frame.moderate_threshold_m).astype(int)
        self.assertTrue(np.array_equal(frame.target.to_numpy(), expected.to_numpy()))
        self.assertEqual(frame.station_code.nunique(), 5)

    def test_food_security_label_matches_frozen_definition(self) -> None:
        frame = self.frames["food_security"]
        expected = (frame.target_ipc3plus_percentage >= 0.20).astype(int)
        self.assertTrue(np.array_equal(frame.target.to_numpy(), expected.to_numpy()))
        self.assertEqual(frame.region_id.nunique(), 18)

    def test_artifact_metadata_checksum_matches(self) -> None:
        for track in TRACKS:
            metadata = json.loads((ROOT / "ml" / "artifacts" / track / "model_metadata.json").read_text(encoding="utf-8"))
            artifact = ROOT / metadata["artifact_path"]
            with self.subTest(track=track):
                self.assertEqual(metadata["artifact_checksum_sha256"], sha256(artifact))
                self.assertTrue(metadata["serialization_round_trip_passed"])

    def test_serialized_models_return_valid_probabilities(self) -> None:
        for track, bundle in self.bundles.items():
            sample = self.frames[track].iloc[:25]
            probability = bundle.predict_probability(sample)
            with self.subTest(track=track):
                self.assertEqual(len(probability), len(sample))
                self.assertTrue(np.isfinite(probability).all())
                self.assertTrue(((probability >= 0.0) & (probability <= 1.0)).all())

    def test_serialized_model_predictions_are_reproducible(self) -> None:
        for track, bundle in self.bundles.items():
            sample = self.frames[track].iloc[:10]
            first = bundle.predict_probability(sample)
            second_bundle = joblib.load(ROOT / "ml" / "artifacts" / track / f"{track}_model_v1.1.0.joblib")
            with self.subTest(track=track):
                np.testing.assert_allclose(first, second_bundle.predict_probability(sample), rtol=0.0, atol=0.0)

    def test_missing_required_schema_field_fails_closed(self) -> None:
        track = "flood"
        sample = self.frames[track].iloc[:1].drop(columns=[FEATURES[track][0]])
        with self.assertRaises(KeyError):
            self.bundles[track].predict_probability(sample)

    def test_insufficient_features_withhold_probability(self) -> None:
        for track, bundle in self.bundles.items():
            sample = self.frames[track].iloc[[0]].copy()
            sample.loc[:, bundle.critical_features] = np.nan
            output = bundle.predict(sample)[0]
            with self.subTest(track=track):
                self.assertEqual(output["data_quality"], "INSUFFICIENT")
                self.assertIsNone(output["probability"])
                self.assertIsNone(output["risk_level"])

    def test_corrupt_artifact_does_not_deserialize(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt.joblib"
            path.write_bytes(b"not-a-valid-joblib-artifact")
            with self.assertRaises(Exception):
                joblib.load(path)

    def test_explanations_include_global_and_local_outputs(self) -> None:
        for track in TRACKS:
            explanation = json.loads((ROOT / "ml" / "artifacts" / track / "explainability.json").read_text(encoding="utf-8"))
            with self.subTest(track=track):
                self.assertGreater(len(explanation["global_feature_importance"]), 0)
                self.assertGreater(len(explanation["local_explanations"]), 0)
                self.assertEqual(explanation["shap_status"], "NOT_APPLICABLE")

    def test_rolling_backtests_are_expanding_and_complete(self) -> None:
        for track in TRACKS:
            report = json.loads((ROOT / "ml" / "artifacts" / track / "backtest_summary.json").read_text(encoding="utf-8"))
            predictions = pd.read_csv(ROOT / report["predictions_path"])
            with self.subTest(track=track):
                self.assertGreaterEqual(report["fold_count"], ACCEPTANCE["common"]["minimum_backtest_folds"])
                expected_tp = int(((predictions.target == 1) & (predictions.prediction == 1)).sum())
                expected_fp = int(((predictions.target == 0) & (predictions.prediction == 1)).sum())
                self.assertEqual(report["overall_metrics"]["true_positive"], expected_tp)
                self.assertEqual(report["overall_metrics"]["false_positive"], expected_fp)
                self.assertEqual(report["overall_metrics"]["threshold"], "fold_specific_validation_thresholds")
                for fold in report["folds"]:
                    self.assertLess(fold["train_end_year"], fold["validation_year"])
                    self.assertLess(fold["validation_year"], fold["test_year"])

    def test_calibration_never_degrades_frozen_test_brier(self) -> None:
        maximum = ACCEPTANCE["common"]["maximum_calibrated_brier_degradation"]
        for track in TRACKS:
            report = json.loads((ROOT / "ml" / "artifacts" / track / "calibration.json").read_text(encoding="utf-8"))
            with self.subTest(track=track):
                self.assertLessEqual(report["test_brier_after"] - report["test_brier_before"], maximum + 1e-12)


if __name__ == "__main__":
    unittest.main()
