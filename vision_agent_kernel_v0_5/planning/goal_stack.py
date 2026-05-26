from __future__ import annotations


class GoalStack:
    """Simple LIFO goal stack with duplicate and cycle prevention.

    Part of Phase 3 of the Unified Execution Plan.
    """

    def __init__(self) -> None:
        self._stack: list[str] = []

    def push(self, goal: str) -> None:
        """Pushes a goal to the stack, removing duplicates to prevent cycle lockups."""
        if goal in self._stack:
            self._stack.remove(goal)
        self._stack.append(goal)

    def pop(self) -> str | None:
        """Pops the top goal off the stack."""
        return self._stack.pop() if self._stack else None

    def peek(self) -> str | None:
        """Peeks at the top goal on the stack without popping it."""
        return self._stack[-1] if self._stack else None

    def clear(self) -> None:
        """Clears the stack."""
        self._stack.clear()

    @property
    def size(self) -> int:
        return len(self._stack)

    def to_list(self) -> list[str]:
        return list(self._stack)
