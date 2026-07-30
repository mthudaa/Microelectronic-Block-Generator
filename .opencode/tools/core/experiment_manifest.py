from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar


class ExperimentStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    NOT_RUN = "NOT RUN"
    NOT_AVAILABLE = "NOT AVAILABLE"


class PromptLevel(str, Enum):
    MINIMAL = "minimal"
    CONSTRAINT_BASED = "constraint-based"
    DETAILED = "detailed"


@dataclass
class ArtifactPaths:
    prompt: str | None = None
    netlist: str | None = None
    circuit_graph: str | None = None
    gds: str | None = None
    pre_simulation: str | None = None
    drc: str | None = None
    lvs: str | None = None
    pex: str | None = None
    post_simulation: str | None = None

    _FIELDS: ClassVar[tuple[str, ...]] = (
        "prompt",
        "netlist",
        "circuit_graph",
        "gds",
        "pre_simulation",
        "drc",
        "lvs",
        "pex",
        "post_simulation",
    )

    def set(self, artifact_name: str, relative_path: str | Path) -> None:
        if artifact_name not in self._FIELDS:
            raise ValueError(
                f"Unsupported artifact name: {artifact_name}. "
                f"Expected one of: {', '.join(self._FIELDS)}"
            )

        normalized = normalize_artifact_path(relative_path)
        setattr(self, artifact_name, normalized)

    def to_dict(self) -> dict[str, str]:
        result: dict[str, str] = {}

        for field_name in self._FIELDS:
            value = getattr(self, field_name)

            if value is not None:
                result[field_name] = value

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactPaths:
        artifacts = cls()

        for field_name in cls._FIELDS:
            value = data.get(field_name)

            if value is not None:
                artifacts.set(field_name, str(value))

        return artifacts


@dataclass
class ExperimentManifest:
    experiment_id: str
    model: str
    prompt_level: PromptLevel

    pdk: str = "gf180mcuD"

    api_calls: int = 0
    refinement_iterations: int = 0
    max_refinement_iterations: int = 2

    netlist_valid: bool = False
    pre_simulation_status: ExperimentStatus = ExperimentStatus.NOT_RUN

    gds_generated: bool = False
    drc_status: ExperimentStatus = ExperimentStatus.NOT_RUN
    lvs_status: ExperimentStatus = ExperimentStatus.NOT_RUN
    pex_status: ExperimentStatus = ExperimentStatus.NOT_RUN
    post_simulation_status: ExperimentStatus = ExperimentStatus.NOT_RUN

    llm_runtime_seconds: float | None = None
    total_runtime_seconds: float | None = None

    final_status: ExperimentStatus = ExperimentStatus.PARTIAL
    artifacts: ArtifactPaths = field(default_factory=ArtifactPaths)

    created_at: str = field(default_factory=lambda: utc_now_iso())
    updated_at: str = field(default_factory=lambda: utc_now_iso())

    metadata: dict[str, Any] = field(default_factory=dict)

    _STAGE_FIELDS: ClassVar[dict[str, str]] = {
        "pre_simulation": "pre_simulation_status",
        "drc": "drc_status",
        "lvs": "lvs_status",
        "pex": "pex_status",
        "post_simulation": "post_simulation_status",
    }

    def record_llm_call(
        self,
        *,
        runtime_seconds: float | None = None,
        refinement: bool = False,
    ) -> None:
        self.api_calls += 1

        if refinement:
            self.refinement_iterations += 1

        if self.refinement_iterations > self.max_refinement_iterations:
            raise ValueError(
                "Refinement iteration limit exceeded: "
                f"{self.refinement_iterations} > "
                f"{self.max_refinement_iterations}"
            )

        if runtime_seconds is not None:
            if runtime_seconds < 0:
                raise ValueError("LLM runtime cannot be negative")

            current_runtime = self.llm_runtime_seconds or 0.0
            self.llm_runtime_seconds = current_runtime + runtime_seconds

        self.touch()

    def mark_netlist(
        self,
        *,
        valid: bool,
        artifact_path: str | Path | None = None,
    ) -> None:
        self.netlist_valid = valid

        if artifact_path is not None:
            self.artifacts.set("netlist", artifact_path)

        self.touch()

    def mark_gds(
        self,
        *,
        generated: bool,
        artifact_path: str | Path | None = None,
    ) -> None:
        self.gds_generated = generated

        if artifact_path is not None:
            self.artifacts.set("gds", artifact_path)

        self.touch()

    def set_artifact(
        self,
        artifact_name: str,
        artifact_path: str | Path,
    ) -> None:
        self.artifacts.set(artifact_name, artifact_path)
        self.touch()

    def set_stage(
        self,
        stage_name: str,
        status: ExperimentStatus | str,
        *,
        artifact_path: str | Path | None = None,
    ) -> None:
        if stage_name not in self._STAGE_FIELDS:
            raise ValueError(
                f"Unsupported stage: {stage_name}. "
                f"Expected one of: {', '.join(self._STAGE_FIELDS)}"
            )

        parsed_status = parse_status(status)
        field_name = self._STAGE_FIELDS[stage_name]
        setattr(self, field_name, parsed_status)

        if artifact_path is not None:
            self.artifacts.set(stage_name, artifact_path)

        self.touch()

    def finalize(
        self,
        *,
        total_runtime_seconds: float | None = None,
    ) -> ExperimentStatus:
        if total_runtime_seconds is not None:
            if total_runtime_seconds < 0:
                raise ValueError("Total runtime cannot be negative")

            self.total_runtime_seconds = total_runtime_seconds

        self.final_status = self.infer_final_status()
        self.touch()
        self.validate()

        return self.final_status

    def infer_final_status(self) -> ExperimentStatus:
        stage_statuses = (
            self.pre_simulation_status,
            self.drc_status,
            self.lvs_status,
            self.pex_status,
            self.post_simulation_status,
        )

        if any(status == ExperimentStatus.FAIL for status in stage_statuses):
            return ExperimentStatus.FAIL

        if not self.netlist_valid:
            return ExperimentStatus.FAIL

        all_physical_stages_passed = (
            self.gds_generated
            and all(
                status == ExperimentStatus.PASS
                for status in stage_statuses
            )
        )

        if all_physical_stages_passed:
            return ExperimentStatus.PASS

        return ExperimentStatus.PARTIAL

    def validate(self) -> None:
        validate_experiment_id(self.experiment_id)

        if not self.model.strip():
            raise ValueError("Model identifier cannot be empty")

        if self.pdk != "gf180mcuD":
            raise ValueError(
                f"Unsupported PDK '{self.pdk}'; expected 'gf180mcuD'"
            )

        if self.api_calls < 0:
            raise ValueError("api_calls cannot be negative")

        if self.refinement_iterations < 0:
            raise ValueError(
                "refinement_iterations cannot be negative"
            )

        if self.max_refinement_iterations < 0:
            raise ValueError(
                "max_refinement_iterations cannot be negative"
            )

        if (
            self.refinement_iterations
            > self.max_refinement_iterations
        ):
            raise ValueError(
                "refinement_iterations exceeds "
                "max_refinement_iterations"
            )

        if (
            self.api_calls > 0
            and self.api_calls < self.refinement_iterations + 1
        ):
            raise ValueError(
                "api_calls must include the initial call and all "
                "refinement calls"
            )

        validate_runtime(
            "llm_runtime_seconds",
            self.llm_runtime_seconds,
        )
        validate_runtime(
            "total_runtime_seconds",
            self.total_runtime_seconds,
        )

        if (
            self.llm_runtime_seconds is not None
            and self.total_runtime_seconds is not None
            and self.total_runtime_seconds
            < self.llm_runtime_seconds
        ):
            raise ValueError(
                "total_runtime_seconds cannot be less than "
                "llm_runtime_seconds"
            )

        for artifact_name, artifact_path in (
            self.artifacts.to_dict().items()
        ):
            try:
                normalize_artifact_path(artifact_path)
            except ValueError as error:
                raise ValueError(
                    f"Invalid {artifact_name} artifact path: {error}"
                ) from error

        if self.final_status == ExperimentStatus.PASS:
            self._validate_pass_status()

        # Ensure custom metadata is JSON serializable.
        try:
            json.dumps(self.metadata)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "metadata must contain JSON-serializable values"
            ) from error

    def _validate_pass_status(self) -> None:
        if self.api_calls < 1:
            raise ValueError(
                "PASS requires at least one recorded API call"
            )

        if not self.netlist_valid:
            raise ValueError(
                "PASS requires netlist_valid to be true"
            )

        if not self.gds_generated:
            raise ValueError(
                "PASS requires gds_generated to be true"
            )

        stage_statuses = {
            "pre_simulation_status":
                self.pre_simulation_status,
            "drc_status": self.drc_status,
            "lvs_status": self.lvs_status,
            "pex_status": self.pex_status,
            "post_simulation_status":
                self.post_simulation_status,
        }

        incomplete = [
            name
            for name, status in stage_statuses.items()
            if status != ExperimentStatus.PASS
        ]

        if incomplete:
            raise ValueError(
                "PASS requires all stages to pass. "
                f"Incomplete stages: {', '.join(incomplete)}"
            )

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        self.validate()

        result: dict[str, Any] = {
            "experiment_id": self.experiment_id,
            "model": self.model,
            "pdk": self.pdk,
            "prompt_level": self.prompt_level.value,
            "api_calls": self.api_calls,
            "refinement_iterations":
                self.refinement_iterations,
            "max_refinement_iterations":
                self.max_refinement_iterations,
            "netlist_valid": self.netlist_valid,
            "pre_simulation_status":
                self.pre_simulation_status.value,
            "gds_generated": self.gds_generated,
            "drc_status": self.drc_status.value,
            "lvs_status": self.lvs_status.value,
            "pex_status": self.pex_status.value,
            "post_simulation_status":
                self.post_simulation_status.value,
            "final_status": self.final_status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "artifacts": self.artifacts.to_dict(),
        }

        if self.llm_runtime_seconds is not None:
            result["llm_runtime_seconds"] = round(
                self.llm_runtime_seconds,
                6,
            )

        if self.total_runtime_seconds is not None:
            result["total_runtime_seconds"] = round(
                self.total_runtime_seconds,
                6,
            )

        if self.metadata:
            result["metadata"] = self.metadata

        return result

    def write(
        self,
        experiment_directory: str | Path,
        *,
        repository_root: str | Path,
    ) -> Path:
        repository = Path(repository_root).resolve()
        output_directory = Path(experiment_directory).resolve()

        ensure_inside_repository(
            repository=repository,
            target=output_directory,
        )

        output_directory.mkdir(parents=True, exist_ok=True)
        output_path = output_directory / "experiment.json"

        payload = json.dumps(
            self.to_dict(),
            indent=2,
            sort_keys=False,
        )
        payload += "\n"

        atomic_write_text(output_path, payload)
        return output_path

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> ExperimentManifest:
        artifacts_data = data.get("artifacts", {})

        if not isinstance(artifacts_data, dict):
            raise ValueError("artifacts must be a JSON object")

        metadata = data.get("metadata", {})

        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a JSON object")

        manifest = cls(
            experiment_id=require_string(
                data,
                "experiment_id",
            ),
            model=require_string(data, "model"),
            pdk=require_string(data, "pdk"),
            prompt_level=PromptLevel(
                require_string(data, "prompt_level")
            ),
            api_calls=require_integer(data, "api_calls"),
            refinement_iterations=require_integer(
                data,
                "refinement_iterations",
            ),
            max_refinement_iterations=require_integer(
                data,
                "max_refinement_iterations",
            ),
            netlist_valid=require_boolean(
                data,
                "netlist_valid",
            ),
            pre_simulation_status=parse_status(
                require_string(
                    data,
                    "pre_simulation_status",
                )
            ),
            gds_generated=require_boolean(
                data,
                "gds_generated",
            ),
            drc_status=parse_status(
                require_string(data, "drc_status")
            ),
            lvs_status=parse_status(
                require_string(data, "lvs_status")
            ),
            pex_status=parse_status(
                require_string(data, "pex_status")
            ),
            post_simulation_status=parse_status(
                require_string(
                    data,
                    "post_simulation_status",
                )
            ),
            final_status=parse_status(
                require_string(data, "final_status")
            ),
            llm_runtime_seconds=optional_number(
                data,
                "llm_runtime_seconds",
            ),
            total_runtime_seconds=optional_number(
                data,
                "total_runtime_seconds",
            ),
            artifacts=ArtifactPaths.from_dict(
                artifacts_data
            ),
            created_at=str(
                data.get("created_at", utc_now_iso())
            ),
            updated_at=str(
                data.get("updated_at", utc_now_iso())
            ),
            metadata=metadata,
        )

        manifest.validate()
        return manifest

    @classmethod
    def load(
        cls,
        experiment_json: str | Path,
        *,
        repository_root: str | Path,
    ) -> ExperimentManifest:
        repository = Path(repository_root).resolve()
        input_path = Path(experiment_json).resolve()

        ensure_inside_repository(
            repository=repository,
            target=input_path,
        )

        if input_path.name != "experiment.json":
            raise ValueError(
                "Manifest path must point to experiment.json"
            )

        try:
            data = json.loads(
                input_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Invalid JSON in {input_path}: {error}"
            ) from error

        if not isinstance(data, dict):
            raise ValueError(
                "experiment.json root value must be an object"
            )

        return cls.from_dict(data)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )


def make_experiment_id(
    circuit_name: str,
    prompt_level: PromptLevel | str,
    *,
    timestamp: datetime | None = None,
) -> str:
    level = (
        prompt_level.value
        if isinstance(prompt_level, PromptLevel)
        else PromptLevel(prompt_level).value
    )

    circuit_slug = slugify(circuit_name)
    level_slug = slugify(level)

    current = timestamp or datetime.now(timezone.utc)
    time_suffix = current.strftime("%Y%m%d-%H%M%S")

    experiment_id = (
        f"{circuit_slug}-{level_slug}-{time_suffix}"
    )

    validate_experiment_id(experiment_id)
    return experiment_id


def slugify(value: str) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")

    if not slug:
        raise ValueError(
            "Cannot create a slug from an empty value"
        )

    return slug


def validate_experiment_id(experiment_id: str) -> None:
    pattern = re.compile(r"^[a-z0-9][a-z0-9-]{2,127}$")

    if not pattern.fullmatch(experiment_id):
        raise ValueError(
            "experiment_id must contain 3-128 lowercase "
            "alphanumeric or hyphen characters"
        )


def normalize_artifact_path(
    artifact_path: str | Path,
) -> str:
    raw = str(artifact_path).strip()

    if not raw:
        raise ValueError("Artifact path cannot be empty")

    candidate = Path(raw)

    if candidate.is_absolute():
        raise ValueError(
            "Artifact path must be relative"
        )

    normalized_parts = [
        part
        for part in candidate.parts
        if part not in ("", ".")
    ]

    if ".." in normalized_parts:
        raise ValueError(
            "Parent-directory traversal is not allowed"
        )

    normalized = Path(*normalized_parts).as_posix()
    lowered = normalized.lower()

    if (
        lowered == ".env"
        or lowered.startswith(".env.")
        or "/.env" in lowered
        or lowered.endswith(".pem")
        or lowered.endswith(".key")
    ):
        raise ValueError(
            "Credential and secret paths are not allowed"
        )

    return normalized


def ensure_inside_repository(
    *,
    repository: Path,
    target: Path,
) -> None:
    try:
        target.relative_to(repository)
    except ValueError as error:
        raise ValueError(
            f"Path is outside repository: {target}"
        ) from error


def atomic_write_text(
    output_path: Path,
    content: str,
) -> None:
    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)

        os.replace(temporary_path, output_path)

    except Exception:
        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            temporary_path.unlink()

        raise


def parse_status(
    value: ExperimentStatus | str,
) -> ExperimentStatus:
    if isinstance(value, ExperimentStatus):
        return value

    return ExperimentStatus(str(value).upper())


def validate_runtime(
    field_name: str,
    value: float | None,
) -> None:
    if value is not None and value < 0:
        raise ValueError(
            f"{field_name} cannot be negative"
        )


def require_string(
    data: dict[str, Any],
    field_name: str,
) -> str:
    value = data.get(field_name)

    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be a non-empty string"
        )

    return value.strip()


def require_integer(
    data: dict[str, Any],
    field_name: str,
) -> int:
    value = data.get(field_name)

    if (
        not isinstance(value, int)
        or isinstance(value, bool)
    ):
        raise ValueError(
            f"{field_name} must be an integer"
        )

    return value


def require_boolean(
    data: dict[str, Any],
    field_name: str,
) -> bool:
    value = data.get(field_name)

    if not isinstance(value, bool):
        raise ValueError(
            f"{field_name} must be a boolean"
        )

    return value


def optional_number(
    data: dict[str, Any],
    field_name: str,
) -> float | None:
    value = data.get(field_name)

    if value is None:
        return None

    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
    ):
        raise ValueError(
            f"{field_name} must be numeric or null"
        )

    return float(value)