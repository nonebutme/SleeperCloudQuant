"""Backtest request and response payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.backtest.models import BacktestResultSummary, BatchBacktestRunSummary


@dataclass(frozen=True, slots=True)
class BacktestRunRequestPayload:
    """Minimal request payload for one backtest submission."""

    run_id: str
    strategy_name: str
    symbol: str
    benchmark: str
    start_date: str
    end_date: str
    initial_cash: float = 1_000_000
    frequency: str = "1d"
    parameters: dict[str, Any] = field(default_factory=dict)
    extra_config: dict[str, Any] = field(default_factory=dict)
    strategy_id: str | None = None
    strategy_version: str | None = None


@dataclass(frozen=True, slots=True)
class BacktestRunResponsePayload:
    """Minimal response payload for one backtest submission."""

    result: BacktestResultSummary


@dataclass(frozen=True, slots=True)
class SingleBacktestTaskCreateRequestPayload:
    """Create one persisted one-symbol backtest task."""

    task_id: str | None = None
    run_id: str | None = None
    name: str = ""
    strategy_name: str = "moving_average_strategy"
    strategy_id: str | None = None
    strategy_version: str | None = None
    symbol: str = "000001.XSHE"
    benchmark: str = "000300.XSHG"
    start_date: str = "2020-01-01"
    end_date: str = "2020-12-31"
    initial_cash: float = 1_000_000
    frequency: str = "1d"
    adjustment: str = "qfq"
    parameters: dict[str, Any] = field(default_factory=dict)
    extra_config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SingleBacktestTaskRunRequestPayload:
    """Start or retry one persisted single-symbol task."""

    wait: bool = False


@dataclass(frozen=True, slots=True)
class SingleBacktestTaskListQueryPayload:
    """List recent persisted single-symbol tasks."""

    limit: int = 50


@dataclass(frozen=True, slots=True)
class SingleBacktestTaskResponsePayload:
    """One persisted single-symbol task."""

    task: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SingleBacktestTaskListResponsePayload:
    """Persisted single-symbol task list."""

    tasks: list[dict[str, Any]] = field(default_factory=list)

@dataclass(frozen=True, slots=True)
class BacktestResultPanelResponsePayload:
    """Aggregated result panel for one persisted backtest run."""

    result: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BacktestPortfolioPanelResponsePayload:
    """Aggregated portfolio panel for runs sharing one prefix."""

    result: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BacktestResultTableQueryPayload:
    """Query one persisted result table with pagination/export options."""

    table: str = "trades"
    offset: int = 0
    limit: int = 50
    export_format: str = "json"


@dataclass(frozen=True, slots=True)
class BacktestResultTableResponsePayload:
    """Paginated table rows or serialized export content."""

    result: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BacktestInputSnapshotResponsePayload:
    """Persisted input data snapshot for one backtest run."""

    snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BacktestDataAssetDirectoryQueryPayload:
    """Query persisted local data asset directory."""

    symbol: str | None = None
    dataset: str | None = None
    data_version: str | None = None
    quality_status: str | None = None
    coverage_status: str | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class BacktestDataAssetDirectoryResponsePayload:
    """Persisted local data asset directory response."""

    assets: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BacktestInputSnapshotMigrationRequestPayload:
    """Request a dry-run or write migration for historical backtest input snapshots."""

    run_id_prefix: str | None = None
    dry_run: bool = True
    limit: int = 100


@dataclass(frozen=True, slots=True)
class BacktestInputSnapshotMigrationResponsePayload:
    """Historical input snapshot migration diagnostics."""

    result: dict[str, Any] = field(default_factory=dict)
@dataclass(frozen=True, slots=True)
class BacktestExperimentPanelResponsePayload:
    """Experiment/run group summary for one run_id prefix."""

    result: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BacktestExperimentIndexCreateRequestPayload:
    """Create or update one local backtest experiment index entry."""

    experiment_id: str | None = None
    run_id_prefix: str = ""
    name: str = "本地回测实验"
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    task_id: str | None = None
    primary_run_id: str | None = None


@dataclass(frozen=True, slots=True)
class BacktestExperimentIndexFilterPayload:
    """Filter local experiment index entries."""

    search: str | None = None
    tag: str | None = None
    status: str | None = None
    include_archived: bool = False


@dataclass(frozen=True, slots=True)
class BacktestExperimentIndexUpdateRequestPayload:
    """Update local experiment index metadata."""

    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    status: str | None = None
    archived: bool | None = None
    review_note: str | None = None


@dataclass(frozen=True, slots=True)
class BacktestExperimentCompareRequestPayload:
    """Compare selected local experiments."""

    experiment_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class BacktestExperimentCompareResponsePayload:
    """Experiment comparison response."""

    result: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BacktestExperimentIndexResponsePayload:
    """Single experiment index response."""

    experiment: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BacktestExperimentIndexListResponsePayload:
    """Experiment index list response."""

    experiments: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class StrategyDefinitionPayload:
    """Editable strategy definition exposed by the MVP strategy library."""

    strategy_id: str
    name: str
    category: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    parameter_schema: dict[str, Any] = field(default_factory=dict)
    source_code: str = ""
    source_reference: str = "SleeperCloudQuant-old"
    editable: bool = True
    latest_version: str = "v1"
    version_count: int = 1
    saved_at: str | None = None
    source_sha256: str | None = None
    validation_status: str = "unknown"
    execution_contract: str = "target-weights-v1"


@dataclass(frozen=True, slots=True)
class StrategyLibraryResponsePayload:
    """Strategy library listing response."""

    strategies: list[StrategyDefinitionPayload] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class StrategySaveRequestPayload:
    """Save one editable strategy draft."""

    strategy_id: str
    name: str
    source_code: str
    category: str = "自定义策略"
    description: str = "本地自定义 Python 策略。"
    parameters: dict[str, Any] = field(default_factory=dict)
    parameter_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StrategyValidateRequestPayload:
    """Validate source code against the local strategy contract."""

    source_code: str


@dataclass(frozen=True, slots=True)
class StrategyValidateResponsePayload:
    """Structured strategy validation result."""

    validation: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StrategySaveResponsePayload:
    """Save result for one editable strategy draft."""

    strategy: StrategyDefinitionPayload
    status: str = "draft_saved"


@dataclass(frozen=True, slots=True)
class StrategyVersionHistoryResponsePayload:
    """Version history for one editable strategy."""

    strategy_id: str
    versions: list[StrategyDefinitionPayload] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class IndependentScreeningTaskCreateRequestPayload:
    """Create one frozen-universe independent-capital screening task."""

    task_id: str | None = None
    name: str = "A股独立账户批量回测"
    strategy_id: str = "moving_average_strategy"
    strategy_version: str | None = None
    symbols: list[str] = field(default_factory=list)
    market: str = ""
    start_date: str = "2020-01-01"
    end_date: str = "2020-12-31"
    adjustment: str = "raw"
    benchmark: str = "000300.XSHG"
    initial_cash: float = 1_000_000
    parameters: dict[str, Any] = field(default_factory=dict)
    max_workers: int = 4
    retry_count: int = 1
    symbol_limit: int = 0
    scheduler_batch_size: int = 0


@dataclass(frozen=True, slots=True)
class IndependentScreeningTaskRunRequestPayload:
    """Start or resume one independent screening task."""

    wait: bool = False


@dataclass(frozen=True, slots=True)
class IndependentScreeningRetryRequestPayload:
    """Retry selected retryable per-symbol failures."""

    symbols: list[str] = field(default_factory=list)
    wait: bool = False


@dataclass(frozen=True, slots=True)
class IndependentScreeningTaskControlRequestPayload:
    """Pause, resume, or cancel one screening task."""

    action: str = "pause"


@dataclass(frozen=True, slots=True)
class IndependentScreeningTaskListQueryPayload:
    """List recent independent screening tasks."""

    limit: int = 30


@dataclass(frozen=True, slots=True)
class IndependentScreeningItemQueryPayload:
    """Page per-symbol screening results."""

    entered_only: bool = False
    status: str = ""
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True, slots=True)
class IndependentScreeningTaskResponsePayload:
    """Single screening task response."""

    task: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IndependentScreeningTaskListResponsePayload:
    """Screening task list response."""

    tasks: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class IndependentScreeningItemsResponsePayload:
    """Paged screening item response."""

    result: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SharedPortfolioTaskCreateRequestPayload:
    """Create one frozen-universe shared-cash portfolio task."""

    task_id: str | None = None
    name: str = "A-share shared-cash portfolio"
    strategy_id: str = "moving_average_strategy"
    strategy_version: str | None = None
    symbols: list[str] = field(default_factory=list)
    market: str = ""
    start_date: str = "2020-01-01"
    end_date: str = "2020-12-31"
    adjustment: str = "raw"
    benchmark: str = "000300.XSHG"
    initial_cash: float = 1_000_000
    parameters: dict[str, Any] = field(default_factory=dict)
    max_workers: int = 4
    symbol_limit: int = 20
    max_positions: int = 10
    portfolio_exposure: float = 0.95
    commission_rate: float = 0.0003
    min_commission: float = 5.0
    tax_rate: float = 0.001
    slippage_rate: float = 0.0005
    rebalance_policy: str | None = None
    capacity_replacement_policy: str | None = None
    max_single_position_weight: float | None = None


@dataclass(frozen=True, slots=True)
class SharedPortfolioTaskRunRequestPayload:
    """Start or resume one shared portfolio task."""

    wait: bool = False


@dataclass(frozen=True, slots=True)
class SharedPortfolioTaskListQueryPayload:
    """List recent shared portfolio tasks."""

    limit: int = 30


@dataclass(frozen=True, slots=True)
class SharedPortfolioTaskResponsePayload:
    """Single shared portfolio task response."""

    task: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SharedPortfolioTaskListResponsePayload:
    """Shared portfolio task list response."""

    tasks: list[dict[str, Any]] = field(default_factory=list)

@dataclass(frozen=True, slots=True)
class BacktestModeTaskDirectoryQueryPayload:
    """Filter the unified directory of both backtest modes."""

    mode: str = ""
    status: str = ""
    strategy_id: str = ""
    search: str = ""
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class BacktestModeTaskDirectoryResponsePayload:
    """Unified task directory response."""

    tasks: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ParameterMatrixTaskCreateRequestPayload:
    """Create one managed parameter-matrix backtest task."""

    task_id: str | None = None
    run_id_prefix: str = "parameter-matrix"
    strategy_name: str = "moving_average_strategy"
    symbol: str = "000001.XSHE"
    benchmark: str = "000300.XSHG"
    start_date: str = "2020-01-01"
    end_date: str = "2020-12-31"
    parameter_grid: dict[str, list[Any]] = field(default_factory=dict)
    base_parameters: dict[str, Any] = field(default_factory=dict)
    extra_config: dict[str, Any] = field(default_factory=dict)
    strategy_id: str | None = None
    strategy_version: str | None = None
    initial_cash: float = 1_000_000
    frequency: str = "1d"
    max_runs: int = 24


@dataclass(frozen=True, slots=True)
class ParameterMatrixTaskRunRequestPayload:
    """Run one managed parameter-matrix task."""

    rerun_failed_only: bool = False
    max_runs: int | None = None


@dataclass(frozen=True, slots=True)
class ParameterMatrixTaskResponsePayload:
    """Single parameter-matrix task response."""

    task: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParameterMatrixTaskListResponsePayload:
    """List parameter-matrix tasks."""

    tasks: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ParameterMatrixTaskRunResponsePayload:
    """Parameter-matrix run response."""

    result: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ParameterScanRequestPayload:
    """Run a small parameter-grid scan for one strategy."""

    run_id_prefix: str
    strategy_name: str
    symbol: str
    benchmark: str
    start_date: str
    end_date: str
    parameter_grid: dict[str, list[Any]] = field(default_factory=dict)
    base_parameters: dict[str, Any] = field(default_factory=dict)
    extra_config: dict[str, Any] = field(default_factory=dict)
    strategy_id: str | None = None
    strategy_version: str | None = None
    initial_cash: float = 1_000_000
    frequency: str = "1d"
    max_runs: int = 12


@dataclass(frozen=True, slots=True)
class ParameterScanResponsePayload:
    """Parameter-grid scan response."""

    run_id_prefix: str
    results: list[BacktestResultSummary] = field(default_factory=list)
    combinations: list[dict[str, Any]] = field(default_factory=list)
    status: str = "completed"


@dataclass(frozen=True, slots=True)
class BatchBacktestRunItemPayload:
    """One batch item payload normalized before execution."""

    run_id: str
    strategy_name: str
    symbol: str
    benchmark: str
    start_date: str
    end_date: str
    initial_cash: float = 1_000_000
    frequency: str = "1d"
    parameters: dict[str, Any] = field(default_factory=dict)
    extra_config: dict[str, Any] = field(default_factory=dict)
    strategy_id: str | None = None
    strategy_version: str | None = None


@dataclass(frozen=True, slots=True)
class BatchBacktestRunRequestPayload:
    """Minimal request payload for one batch backtest submission."""

    experiment_id: str
    profile: str = "custom_batch"
    runs: list[BatchBacktestRunItemPayload] | list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        normalized_runs: list[BatchBacktestRunItemPayload] = []
        for raw in self.runs:
            if isinstance(raw, BatchBacktestRunItemPayload):
                normalized_runs.append(raw)
                continue
            if not isinstance(raw, dict):
                raise ValueError("invalid batch run item")
            try:
                normalized_runs.append(BatchBacktestRunItemPayload(**raw))
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid batch run item") from exc
        if not normalized_runs:
            raise ValueError("batch runs must not be empty")
        run_ids = [item.run_id for item in normalized_runs]
        if len(set(run_ids)) != len(run_ids):
            raise ValueError("batch run_id values must be unique")
        benchmarks = [item.benchmark for item in normalized_runs]
        if len(set(benchmarks)) != 1:
            raise ValueError("batch benchmark values must be consistent")
        strategy_names = [item.strategy_name for item in normalized_runs]
        if len(set(strategy_names)) != 1:
            raise ValueError("batch strategy_name values must be consistent")
        frequencies = [item.frequency for item in normalized_runs]
        if len(set(frequencies)) != 1:
            raise ValueError("batch frequency values must be consistent")
        initial_cash_values = [item.initial_cash for item in normalized_runs]
        if len(set(initial_cash_values)) != 1:
            raise ValueError("batch initial_cash values must be consistent")
        start_dates = [item.start_date for item in normalized_runs]
        if len(set(start_dates)) != 1:
            raise ValueError("batch start_date values must be consistent")
        end_dates = [item.end_date for item in normalized_runs]
        if len(set(end_dates)) != 1:
            raise ValueError("batch end_date values must be consistent")
        parameter_sets = [item.parameters for item in normalized_runs]
        if any(parameters != parameter_sets[0] for parameters in parameter_sets[1:]):
            raise ValueError("batch parameters values must be consistent")
        extra_configs = [item.extra_config for item in normalized_runs]
        if any(extra_config != extra_configs[0] for extra_config in extra_configs[1:]):
            raise ValueError("batch extra_config values must be consistent")
        object.__setattr__(self, "runs", normalized_runs)


@dataclass(frozen=True, slots=True)
class BatchBacktestRunResponsePayload:
    """Minimal response payload for one batch backtest execution."""

    summary: BatchBacktestRunSummary


@dataclass(frozen=True, slots=True)
class StrategyResearchTaskCreateRequestPayload:
    """Create one local strategy research task."""

    task_id: str | None = None
    strategy_id: str = "moving_average_strategy"
    strategy_version: str | None = None
    name: str = "本地策略研究任务"
    symbols: list[str] = field(default_factory=lambda: ["000001.XSHE"])
    start_date: str = "2020-01-01"
    end_date: str = "2020-12-31"
    benchmark: str = "000300.XSHG"
    frequency: str = "1d"
    parameters: dict[str, Any] = field(default_factory=dict)
    indicator_plan: list[dict[str, Any]] = field(default_factory=list)
    signal_rules: list[dict[str, Any]] = field(default_factory=list)
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class StrategyResearchTaskResponsePayload:
    """Strategy research task response."""

    task: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StrategyResearchTaskListResponsePayload:
    """Strategy research task list response."""

    tasks: list[dict[str, Any]] = field(default_factory=list)

@dataclass(frozen=True, slots=True)
class StrategyResearchTaskRunRequestPayload:
    """Run one strategy research task through the local backtest engine."""

    run_id_prefix: str | None = None
    initial_cash: float = 1_000_000
    extra_config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StrategyResearchTaskRunResponsePayload:
    """Strategy research task run response."""

    result: dict[str, Any] = field(default_factory=dict)







