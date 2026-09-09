"""Traffic state machine. Times are monotonic seconds, never frame counts."""
from dataclasses import dataclass


@dataclass
class Settings:
    wait: float = 10
    yellow: float = 3
    clearance: float = 1
    crossing: float = 8
    grace: float = 0.8


class Controller:
    def __init__(self, settings=None):
        self.settings = settings or Settings()
        self.reset()

    def reset(self):
        self.phase = "idle"
        self.entered = None
        self.people = {}
        self.waited = 0
        self.cycles = 0
        self.events = []

    def update(self, now, ids):
        cfg = self.settings
        if self.phase == "idle":
            for key in list(self.people):
                if now - self.people[key][1] > cfg.grace:
                    del self.people[key]
            for key in ids:
                first = self.people.get(key, (now, now))[0]
                self.people[key] = (first, now)
            self.waited = max((now - first for first, _ in self.people.values()), default=0)
            # An absent person cannot trigger a crossing during the grace window.
            if any(now - self.people[key][0] >= cfg.wait for key in ids):
                self.transition("yellow", now)
        else:
            durations = {"yellow": cfg.yellow, "clearance": cfg.clearance,
                         "crossing": cfg.crossing, "return": cfg.clearance}
            following = {"yellow": "clearance", "clearance": "crossing",
                         "crossing": "return", "return": "idle"}
            # Start each phase at the actual update time: never skip a safety phase.
            if now - self.entered >= durations[self.phase]:
                self.transition(following[self.phase], now)
        return self.snapshot(now)

    def transition(self, phase, now):
        self.phase, self.entered = phase, now
        self.events.insert(0, {"phase": phase, "time": now})
        self.events = self.events[:8]
        if phase == "crossing":
            self.cycles += 1
        if phase == "idle":
            self.people.clear()
            self.waited = 0

    def snapshot(self, now):
        durations = {"yellow": self.settings.yellow, "clearance": self.settings.clearance,
                     "crossing": self.settings.crossing, "return": self.settings.clearance}
        return {"phase": self.phase,
                "car": "green" if self.phase == "idle" else "yellow" if self.phase == "yellow" else "red",
                "pedestrian": "green" if self.phase == "crossing" else "red",
                "waited": round(min(self.waited, self.settings.wait), 1),
                "wait_target": self.settings.wait,
                "remaining": round(max(0, durations.get(self.phase, 0) - (now - self.entered)), 1) if self.entered is not None and self.phase != "idle" else 0,
                "cycles": self.cycles, "events": self.events}
