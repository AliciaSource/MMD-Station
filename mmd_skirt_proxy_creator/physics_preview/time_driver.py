from typing import NamedTuple


class StepDecision(NamedTuple):
    step_seconds: float
    reset_required: bool
    source: str


class PreviewDeadlineScheduler:
    def __init__(self, minimum_delay=0.001, max_lag_intervals=1.0):
        if minimum_delay <= 0.0:
            raise ValueError("minimum_delay must be positive")
        if max_lag_intervals < 0.0:
            raise ValueError("max_lag_intervals must be non-negative")
        self.minimum_delay = float(minimum_delay)
        self.max_lag_intervals = float(max_lag_intervals)
        self.deadline = None

    def reset(self):
        self.deadline = None

    def next_delay(self, started, finished, interval):
        started = float(started)
        finished = float(finished)
        interval = float(interval)
        if interval <= 0.0:
            raise ValueError("interval must be positive")
        if self.deadline is None:
            self.deadline = started
        self.deadline += interval
        maximum_lag = interval * self.max_lag_intervals
        if finished - self.deadline > maximum_lag:
            self.deadline = finished
        return max(self.deadline - finished, self.minimum_delay)


class PreviewTimeDriver:
    def __init__(self, fixed_hz=60, max_substeps=10):
        if fixed_hz <= 0:
            raise ValueError("fixed_hz must be positive")
        if max_substeps <= 0:
            raise ValueError("max_substeps must be positive")
        self.fixed_hz = float(fixed_hz)
        self.max_substeps = int(max_substeps)
        self.fixed_step_seconds = 1.0 / self.fixed_hz
        self.last_scene_seconds = None
        self.last_wall_seconds = None
        self.last_playing = None

    def reset(self):
        self.last_scene_seconds = None
        self.last_wall_seconds = None
        self.last_playing = None

    def sample(self, scene_seconds, wall_seconds, playing):
        scene_seconds = float(scene_seconds)
        wall_seconds = float(wall_seconds)
        playing = bool(playing)
        if self.last_playing is None:
            self._remember(scene_seconds, wall_seconds, playing)
            return StepDecision(self.fixed_step_seconds, False, "initial")
        if playing != self.last_playing:
            self._remember(scene_seconds, wall_seconds, playing)
            return StepDecision(0.0, False, "mode-switch")

        scene_delta = scene_seconds - self.last_scene_seconds
        wall_delta = wall_seconds - self.last_wall_seconds
        self._remember(scene_seconds, wall_seconds, playing)
        if playing:
            if scene_delta < -1.0e-9:
                return StepDecision(0.0, True, "timeline-rewind")
            if scene_delta <= 1.0e-9:
                return StepDecision(0.0, False, "timeline-idle")
            return StepDecision(self._clamp_step(scene_delta), False, "timeline")

        if abs(scene_delta) > 1.0e-9:
            return StepDecision(0.0, True, "timeline-seek")
        if wall_delta < 0.0:
            return StepDecision(0.0, True, "clock-rewind")
        return StepDecision(self._clamp_step(wall_delta), False, "wall")

    def _clamp_step(self, value):
        return min(value, self.fixed_step_seconds * self.max_substeps)

    def _remember(self, scene_seconds, wall_seconds, playing):
        self.last_scene_seconds = scene_seconds
        self.last_wall_seconds = wall_seconds
        self.last_playing = playing
