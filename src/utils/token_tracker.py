#!/usr/bin/env python3
"""
Token Guardian - Budget Tracking for Ralph-Lite
Part of Albatross Phase 4 - Core Build

Enforces $5/day spend limit across Ralph-Lite operations.
Persists data to JSON file for resume capability.
"""

import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional


class BudgetExceeded(Exception):
    """Raised when daily token budget exceeded."""
    pass


class TokenGuardian:
    """
    Tracks API costs and enforces daily budget limit.
    Persists data to JSON file for resume capability.
    """

    def __init__(self, daily_limit: float = 5.00,
                 data_dir: str = "~/albatross/config"):
        self.daily_limit = daily_limit
        self.data_dir = Path(data_dir).expanduser()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.costs_file = self.data_dir / "token_costs.json"
        self.today = date.today().isoformat()
        self.daily_costs = self._load_costs()

    def _load_costs(self) -> Dict:
        """Load cost history from JSON file."""
        if not self.costs_file.exists():
            return {"history": {}, "current_date": self.today}

        with open(self.costs_file, 'r') as f:
            data = json.load(f)

        # Reset if new day
        if data.get("current_date") != self.today:
            data = {"history": {}, "current_date": self.today}

        return data

    def _save_costs(self):
        """Save cost history to JSON file."""
        with open(self.costs_file, 'w') as f:
            json.dump(self.daily_costs, f, indent=2)

    def get_daily_spend(self) -> float:
        """Get total spend for today."""
        return sum(
            op.get("cost", 0)
            for op in self.daily_costs.get("history", {}).values()
        )

    def check_budget(self, estimated_cost: float = 0.0) -> bool:
        """
        Check if we can afford this operation.

        Args:
            estimated_cost: Optional cost estimate to check

        Returns:
            True if under budget, False if over
        """
        current = self.get_daily_spend()
        return (current + estimated_cost) < self.daily_limit

    def log_cost(self, operation: str, phase: str,
                 iteration: int, cost: float,
                 build_id: str = None):
        """
        Log a cost for an operation.

        Args:
            operation: e.g., "interview_question", "plan_generation"
            phase: "interview", "planning", "build", "done"
            iteration: iteration number (0 if N/A)
            cost: dollar amount
            build_id: optional build identifier
        """
        timestamp = datetime.now().isoformat()
        op_id = f"{timestamp}_{operation}"

        self.daily_costs["history"][op_id] = {
            "timestamp": timestamp,
            "operation": operation,
            "phase": phase,
            "iteration": iteration,
            "cost": cost,
            "build_id": build_id
        }

        self._save_costs()

    def get_summary(self) -> Dict:
        """Return summary of today's usage."""
        history = self.daily_costs.get("history", {})
        total = sum(op.get("cost", 0) for op in history.values())

        by_phase = {}
        for op in history.values():
            phase = op.get("phase", "unknown")
            by_phase[phase] = by_phase.get(phase, 0) + op.get("cost", 0)

        return {
            "date": self.today,
            "limit": self.daily_limit,
            "spent": total,
            "remaining": self.daily_limit - total,
            "operations_count": len(history),
            "by_phase": by_phase
        }

    def enforce_limit(self, context: str = ""):
        """
        Hard stop if limit reached.

        Raises:
            BudgetExceeded: If daily limit reached
        """
        current = self.get_daily_spend()
        if current >= self.daily_limit:
            msg = f"Daily limit ${self.daily_limit} reached. {context}"
            raise BudgetExceeded(msg)

    def estimate_remaining_iterations(self, avg_cost_per_iter: float = 0.50) -> int:
        """Estimate how many iterations we can afford."""
        remaining = self.daily_limit - self.get_daily_spend()
        if remaining <= 0:
            return 0
        return int(remaining / avg_cost_per_iter)


# Convenience function
def get_guardian() -> TokenGuardian:
    """Get default TokenGuardian instance."""
    return TokenGuardian()


if __name__ == "__main__":
    # Test
    tg = TokenGuardian(daily_limit=5.00)
    print(f"Remaining: ${tg.get_daily_spend():.2f}")

    tg.log_cost("test_op", "test", 1, 0.50)
    print(f"After test: ${tg.get_daily_spend():.2f}")

    print(tg.get_summary())
