from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import importlib.util
import sys

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "core"
    / "experiment_manifest.py"
)

SPEC = importlib.util.spec_from_file_location(
    "mbg_experiment_manifest",
    MODULE_PATH,
)

if SPEC is None or SPEC.loader is None:
    raise RuntimeError(
        f"Unable to load experiment manifest from {MODULE_PATH}"
    )

experiment_manifest = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = experiment_manifest
SPEC.loader.exec_module(experiment_manifest)

ExperimentManifest = experiment_manifest.ExperimentManifest
ExperimentStatus = experiment_manifest.ExperimentStatus
PromptLevel = experiment_manifest.PromptLevel
make_experiment_id = experiment_manifest.make_experiment_id
normalize_artifact_path = (
    experiment_manifest.normalize_artifact_path
)


class ExperimentManifestTests(unittest.TestCase):
    def test_make_experiment_id(self) -> None:
        timestamp = datetime(
            2026,
            7,
            29,
            12,
            30,
            45,
            tzinfo=timezone.utc,
        )

        experiment_id = make_experiment_id(
            "RC Filter",
            PromptLevel.MINIMAL,
            timestamp=timestamp,
        )

        self.assertEqual(
            experiment_id,
            "rc-filter-minimal-20260729-123045",
        )

    def test_partial_manifest(self) -> None:
        manifest = ExperimentManifest(
            experiment_id="rc-filter-minimal-001",
            model="synthetic-test-model",
            prompt_level=PromptLevel.MINIMAL,
        )

        manifest.record_llm_call(runtime_seconds=1.25)
        manifest.mark_netlist(
            valid=True,
            artifact_path="generated_netlist.spice",
        )
        manifest.mark_gds(generated=False)

        status = manifest.finalize(
            total_runtime_seconds=1.75,
        )

        self.assertEqual(
            status,
            ExperimentStatus.PARTIAL,
        )
        self.assertEqual(manifest.api_calls, 1)
        self.assertTrue(manifest.netlist_valid)
        self.assertFalse(manifest.gds_generated)

    def test_refinement_limit(self) -> None:
        manifest = ExperimentManifest(
            experiment_id="comparator-detailed-001",
            model="synthetic-test-model",
            prompt_level=PromptLevel.DETAILED,
            max_refinement_iterations=1,
        )

        manifest.record_llm_call()
        manifest.record_llm_call(refinement=True)

        with self.assertRaisesRegex(
            ValueError,
            "Refinement iteration limit exceeded",
        ):
            manifest.record_llm_call(refinement=True)

    def test_reject_parent_traversal(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "Parent-directory traversal",
        ):
            normalize_artifact_path(
                "../private/experiment.json"
            )

    def test_reject_absolute_artifact_path(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "must be relative",
        ):
            normalize_artifact_path(
                "/home/example/output.gds"
            )

    def test_write_and_load_manifest(self) -> None:
        repository = Path.cwd().resolve()

        with tempfile.TemporaryDirectory(
            dir=repository,
            prefix=".manifest-test-",
        ) as temporary_directory:
            output_directory = (
                Path(temporary_directory)
                / "outputs"
                / "fixture"
            )

            manifest = ExperimentManifest(
                experiment_id="rc-filter-minimal-002",
                model="synthetic-test-model",
                prompt_level=PromptLevel.MINIMAL,
            )

            manifest.set_artifact("prompt", "prompt.txt")
            manifest.record_llm_call(
                runtime_seconds=0.75
            )
            manifest.mark_netlist(
                valid=True,
                artifact_path="generated_netlist.spice",
            )
            manifest.finalize(
                total_runtime_seconds=1.0
            )

            output_path = manifest.write(
                output_directory,
                repository_root=repository,
            )

            self.assertTrue(output_path.exists())
            self.assertEqual(
                output_path.name,
                "experiment.json",
            )

            payload = json.loads(
                output_path.read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                payload["experiment_id"],
                "rc-filter-minimal-002",
            )
            self.assertEqual(
                payload["final_status"],
                "PARTIAL",
            )

            loaded = ExperimentManifest.load(
                output_path,
                repository_root=repository,
            )

            self.assertEqual(
                loaded.experiment_id,
                manifest.experiment_id,
            )
            self.assertEqual(
                loaded.prompt_level,
                PromptLevel.MINIMAL,
            )
            self.assertEqual(
                loaded.final_status,
                ExperimentStatus.PARTIAL,
            )

    def test_reject_write_outside_repository(self) -> None:
        repository = Path.cwd().resolve()

        manifest = ExperimentManifest(
            experiment_id="rc-filter-minimal-003",
            model="synthetic-test-model",
            prompt_level=PromptLevel.MINIMAL,
        )

        with tempfile.TemporaryDirectory() as outside:
            with self.assertRaisesRegex(
                ValueError,
                "outside repository",
            ):
                manifest.write(
                    Path(outside) / "experiment",
                    repository_root=repository,
                )


if __name__ == "__main__":
    unittest.main()