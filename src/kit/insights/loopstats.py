"""Loop numbers per group of ledger entries: runs, shipped, parked, build iterations, errors, stops, $ per stage."""

from __future__ import annotations

import statistics
from collections.abc import Mapping
from dataclasses import dataclass

from kit.bench.windows import Window, contains, parse_utc
from kit.loop.ledger import Entry, StageEntry, StopEntry

STAGES = ("probe", "spec", "plan", "build", "pr")
USAGE_STOPS = ("limit", "usage")
FAILED_STOPS = ("env", "crash")
NAN = float("nan")


@dataclass(frozen=True)
class LoopStats:
    runs: int
    stages: int
    shipped: int
    parked: int
    builds: int
    errors: int
    usage_stops: int
    failed_runs: int
    usd: Mapping[str, float]  # per stage
    peak_k: float  # median peak context of the stage sessions found in transcripts, NaN when none

    @property
    def total_usd(self) -> float:
        return sum(self.usd.values())

    @property
    def finished(self) -> int:
        return self.shipped + self.parked

    @property
    def usd_per_shipped(self) -> float:
        return self.total_usd / self.shipped if self.shipped else NAN

    @property
    def builds_per_shipped(self) -> float:
        return self.builds / self.shipped if self.shipped else NAN

    @property
    def opus_share(self) -> float:
        """Share of loop $ spent in spec and plan (the Opus stages); NaN with no $."""
        total = self.total_usd
        return (self.usd["spec"] + self.usd["plan"]) / total if total else NAN


def stage_entries(entries: list[Entry]) -> list[StageEntry]:
    return [e for e in entries if isinstance(e, StageEntry)]


def stop_entries(entries: list[Entry]) -> list[StopEntry]:
    return [e for e in entries if isinstance(e, StopEntry)]


def usd_by_stage(stages: list[StageEntry]) -> dict[str, float]:
    usd = dict.fromkeys(STAGES, 0.0)
    for e in stages:
        if e.cost is not None:
            usd[e.stage] = usd.get(e.stage, 0.0) + e.cost.usd
    return usd


def median_peak_k(stages: list[StageEntry], peaks: Mapping[str, int]) -> float:
    found = [peaks[e.cost.session_id] / 1000 for e in stages if e.cost is not None and e.cost.session_id in peaks]
    return statistics.median(found) if found else NAN


def loop_stats(entries: list[Entry], peaks: Mapping[str, int]) -> LoopStats:
    """`peaks`: session id -> peak context of that session's main transcript."""
    stages, stops = stage_entries(entries), stop_entries(entries)
    work = [e for e in stages if e.stage != "probe"]
    return LoopStats(
        runs=len(stops),
        stages=len(work),
        shipped=sum(1 for e in work if e.stage == "pr" and e.outcome == "ok"),
        parked=sum(1 for e in work if e.outcome == "park"),
        builds=sum(1 for e in work if e.stage == "build"),
        errors=sum(1 for e in work if e.outcome == "error"),
        usage_stops=sum(1 for e in stops if e.reason in USAGE_STOPS),
        failed_runs=sum(1 for e in stops if e.reason in FAILED_STOPS),
        usd=usd_by_stage(stages),
        peak_k=median_peak_k(work, peaks),
    )


def by_window(entries: list[Entry], windows: list[Window]) -> dict[str, list[Entry]]:
    """Each entry lands in the window holding its time; entries outside every window or with a bad time are dropped."""
    grouped: dict[str, list[Entry]] = {w.name: [] for w in windows}
    for entry in entries:
        moment = parse_utc(entry.time)
        window = next((w for w in windows if moment is not None and contains(w, moment)), None)
        if window is not None:
            grouped[window.name].append(entry)
    return grouped


def by_version(entries: list[Entry]) -> dict[str, list[Entry]]:
    """Entries per recorded kit version, in first-seen order; a blank version is `unknown`."""
    grouped: dict[str, list[Entry]] = {}
    for entry in entries:
        grouped.setdefault(entry.kit_version or "unknown", []).append(entry)
    return grouped


def loop_session_ids(entries: list[Entry]) -> set[str]:
    return {e.cost.session_id for e in stage_entries(entries) if e.cost is not None}
