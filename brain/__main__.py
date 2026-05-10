from __future__ import annotations

from . import UnifiedBrain


def main() -> int:
    brain = UnifiedBrain()
    status = brain.status()
    print("UnifiedBrain initialized")
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
