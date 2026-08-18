"""Token eyeball fixture: comments, strings, numbers, functions, types,
decorators, operators, punctuation."""

import math
from dataclasses import dataclass, field


@dataclass
class NeonRunner:
    """A runner on the grid (docstring)."""

    handle: str
    level: int = 3
    tags: list[str] = field(default_factory=list)

    def signal(self, gain: float = 1.5) -> float:
        # numbers: decimal, hex, float; constants: True, None
        raw = {"grid": [1, 2, 3], "hex": 0xFF, "ok": True, "none": None}
        boost = math.tau * gain**2 - self.level // 2
        text = f"runner={self.handle!r} boost={boost:.3f}\n\t<{len(raw)}>"
        print(text)
        return boost if boost >= 0 else -boost


def main() -> None:
    runner = NeonRunner(handle="nyx", tags=["fast", "quiet"])
    total = sum(runner.signal(g) for g in (0.5, 1.0, 2.0))
    assert total != 0, "dead signal: \"no carrier\""


if __name__ == "__main__":
    main()
