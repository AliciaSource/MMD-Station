from typing import NamedTuple


class StepDecision(NamedTuple):
    step_seconds: float
    reset_required: bool
    source: str


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
