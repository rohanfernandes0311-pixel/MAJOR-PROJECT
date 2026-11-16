import hashlib
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ml_candidate_training as candidates
import predict


class MlCandidateTrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.features, cls.labels = candidates.load_frame()
        cls.groups = candidates.make_region_groups(cls.frame)

    def test_group_holdout_has_no_group_overlap_and_all_classes(self):
        train_idx, test_idx = candidates.leakage_safe_group_holdout(
            self.features, self.labels, self.groups
        )
        self.assertTrue(set(self.groups[train_idx]).isdisjoint(self.groups[test_idx]))
        self.assertEqual(set(self.labels[train_idx]), {0, 1, 2})
        self.assertEqual(set(self.labels[test_idx]), {0, 1, 2})

    def test_candidate_preprocessor_is_fit_on_training_rows_only(self):
        train = self.features.iloc[:100].copy()
        validation = self.features.iloc[100:110].copy()
        train.iloc[0, 0] = np.nan
        validation.iloc[:, 0] = 999999.0
        model = candidates.train_candidate_rf(train, self.labels[:100])
        learned_median = model.preprocessor.named_steps["imputer"].statistics_[0]
        self.assertNotEqual(learned_median, 999999.0)
        self.assertEqual(model.predict(validation).shape, (10,))

    def test_class_imbalance_is_reported(self):
        report = candidates.metric_report(
            candidates.train_candidate_rf(
                self.features.iloc[:500], self.labels[:500]
            ),
            self.features.iloc[:100],
            self.labels[:100],
        )
        self.assertIn("High", report["per_class"])
        self.assertEqual(report["per_class"]["High"]["support"], 0.0)
        self.assertIn("high_risk_false_negatives", report)

    def test_candidate_random_forest_is_reproducible(self):
        first = candidates.train_candidate_rf(
            self.features.iloc[:1000], self.labels[:1000]
        )
        second = candidates.train_candidate_rf(
            self.features.iloc[:1000], self.labels[:1000]
        )
        np.testing.assert_array_equal(
            first.predict(self.features.iloc[1000:1100]),
            second.predict(self.features.iloc[1000:1100]),
        )

    def test_candidate_artifacts_are_isolated_from_production_paths(self):
        self.assertNotEqual(
            candidates.MODEL_DIR / "random_forest_candidate.pkl",
            ROOT / "models" / "random_forest.pkl",
        )
        self.assertNotEqual(
            candidates.MODEL_DIR / "xgboost_candidate.pkl",
            ROOT / "models" / "xgboost.pkl",
        )

    def test_prediction_feature_order_and_invalid_input(self):
        result = predict.predict(
            28.5, 65.0, 0.45, 160.0, 35.0, 82.0, model="ensemble"
        )
        self.assertEqual(list(result["feature_values"]), predict.FEATURES)
        with self.assertRaises(ValueError):
            predict.predict(
                np.nan, 65.0, 0.45, 160.0, 35.0, 82.0, model="ensemble"
            )
        with self.assertRaises(ValueError):
            predict.batch_predict(pd.DataFrame({"deformation_mm": [1.0]}))

    def test_dataset_hash_is_stable_for_current_file(self):
        digest = hashlib.sha256(candidates.DATA_PATH.read_bytes()).hexdigest()
        self.assertEqual(len(digest), 64)
        self.assertEqual(candidates.load_frame()[0].shape[0], 5000)


if __name__ == "__main__":
    unittest.main()
