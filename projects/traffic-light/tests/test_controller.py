import pytest
from app.controller import Controller


class TestController:
    def test_full_cycle_and_no_conflicting_greens(self):
        c = Controller()
        for t in range(101):
            c.update(t / 10, [1])
        assert c.phase == "yellow"
        for t, expected in [(13, "clearance"), (14, "crossing"), (22, "return"), (23, "idle")]:
            s = c.update(t, [])
            assert s["phase"] == expected
            assert not s["car"] == s["pedestrian"] == "green"
        assert c.cycles == 1
        assert c.waited == 0

    def test_different_people_cannot_combine_waits(self):
        c = Controller()
        for t in range(80):
            c.update(t / 10, [1])
        for t in range(80, 141):
            c.update(t / 10, [2])
        assert c.phase == "idle"
        assert c.waited == 6

    def test_short_detection_gap_is_tolerated(self):
        c = Controller()
        c.update(0, [1])
        c.update(.5, [])
        c.update(.7, [1])
        assert c.waited == pytest.approx(.7)
        c.update(2, [])
        c.update(2.1, [1])
        assert c.waited == 0

    def test_absent_person_cannot_trigger(self):
        c = Controller()
        for t in range(100):
            c.update(t / 10, [1])
        c.update(9.9, [1])
        c.update(10.1, [])
        assert c.phase == "idle"

    def test_large_clock_jump_does_not_skip_safety_phase(self):
        c = Controller()
        c.transition("yellow", 0)
        c.update(100, [])
        assert c.phase == "clearance"
        c.update(100.1, [])
        assert c.phase == "clearance"

