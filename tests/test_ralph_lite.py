#!/usr/bin/env python3
"""
Unit tests for Ralph-Lite orchestrator and components.
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.token_tracker import TokenGuardian, BudgetExceeded
from src.core.interview import InterviewGenerator
from src.core.planner import PlanGenerator
from src.core.builder import IterationBuilder, IterationResult
from src.core.ralph_lite import BuildPhase, BuildState, RalphLiteOrchestrator


class TestTokenGuardian:
    """Tests for budget tracking."""

    def test_initialization(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tg = TokenGuardian(daily_limit=5.00, data_dir=tmpdir)
            assert tg.daily_limit == 5.00
            assert tg.get_daily_spend() == 0.0

    def test_log_cost(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tg = TokenGuardian(data_dir=tmpdir)
            tg.log_cost("test_op", "test", 1, 0.50)
            assert tg.get_daily_spend() == 0.50

    def test_check_budget(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tg = TokenGuardian(daily_limit=1.00, data_dir=tmpdir)
            assert tg.check_budget(0.50) is True
            tg.log_cost("op", "test", 1, 0.60)
            assert tg.check_budget(0.50) is False  # Would exceed

    def test_budget_exceeded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tg = TokenGuardian(daily_limit=1.00, data_dir=tmpdir)
            tg.log_cost("op", "test", 1, 1.00)
            with pytest.raises(BudgetExceeded):
                tg.enforce_limit()

    def test_get_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tg = TokenGuardian(daily_limit=5.00, data_dir=tmpdir)
            tg.log_cost("op1", "interview", 1, 0.10)
            tg.log_cost("op2", "build", 1, 0.50)

            summary = tg.get_summary()
            assert summary['spent'] == 0.60
            assert summary['remaining'] == 4.40
            assert summary['operations_count'] == 2


class TestInterviewGenerator:
    """Tests for interview phase."""

    def test_analyze_idea_scraping(self):
        gen = InterviewGenerator()
        result = gen.analyze_idea("Build a scraper for website data")
        assert result["domain"] == "web_scraping"

    def test_analyze_idea_automation(self):
        gen = InterviewGenerator()
        result = gen.analyze_idea("Automate file processing")
        assert result["domain"] == "automation"

    def test_analyze_idea_api(self):
        gen = InterviewGenerator()
        result = gen.analyze_idea("Integrate with external API")
        assert result["domain"] == "api_integration"

    def test_analyze_idea_general(self):
        gen = InterviewGenerator()
        result = gen.analyze_idea("Build something cool")
        assert result["domain"] == "general"

    def test_generate_questions(self):
        gen = InterviewGenerator()
        questions = gen.generate_questions("scrape data from sites")
        assert len(questions) <= 5
        assert all(isinstance(q, str) for q in questions)

    def test_summarize_requirements(self):
        gen = InterviewGenerator()
        qa_pairs = [
            {"question": "What fields?", "answer": "name, price"},
            {"question": "Sources?", "answer": "example.com"}
        ]
        result = gen.summarize_requirements(qa_pairs)
        assert "requirements" in result


class TestPlanGenerator:
    """Tests for planning phase."""

    def test_create_plan_scraping(self):
        pg = PlanGenerator()
        requirements = {
            "domain": "web_scraping",
            "complexity": "medium",
            "requirements": {
                "data_fields": ["title", "price"],
                "sources": ["example.com"],
                "output_format": "CSV"
            }
        }
        plan = pg.create_plan(requirements, "Test Project")
        assert "Test Project" in plan
        assert "Implementation Plan" in plan

    def test_create_plan_general(self):
        pg = PlanGenerator()
        requirements = {
            "domain": "general",
            "complexity": "simple",
            "requirements": {}
        }
        plan = pg.create_plan(requirements, "Generic Tool")
        assert "Generic Tool" in plan

    def test_estimate_iterations(self):
        pg = PlanGenerator()
        assert pg._estimate_iterations("simple") == 5
        assert pg._estimate_iterations("medium") == 7
        assert pg._estimate_iterations("complex") == 10

    def test_revise_plan(self):
        pg = PlanGenerator()
        original = "# Original Plan"
        revised = pg.revise_plan(original, "Add more tests")
        assert "Revision Notes" in revised
        assert "Add more tests" in revised


class TestIterationBuilder:
    """Tests for build phase."""

    def test_create_scaffold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = IterationBuilder(tmpdir)
            result = builder.create_scaffold("test plan", {})
            assert result.success is True
            assert result.iteration_num == 0
            assert len(result.files_created) > 0

    def test_build_iteration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = IterationBuilder(tmpdir)
            # First create scaffold
            scaffold = builder.create_scaffold("plan", {})
            # Then build iteration
            result = builder.build_iteration(1, "Add feature", scaffold.path)
            assert result.iteration_num == 1
            assert result.success is True

    def test_create_final(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = IterationBuilder(tmpdir)
            scaffold = builder.create_scaffold("plan", {})
            final = builder.create_final(scaffold.path)
            assert "FINAL" in final["path"]
            assert Path(final["path"]).exists()

    def test_slugify(self):
        builder = IterationBuilder("/tmp/test")
        assert builder._slugify("Add Error Handling") == "add-error-handling"
        assert len(builder._slugify("A very long task name that exceeds the limit")) <= 30


class TestBuildState:
    """Tests for state management."""

    def test_serialization(self):
        state = BuildState(
            phase=BuildPhase.INTERVIEW,
            project_name="test",
            source_idea="test idea",
            started_at=datetime.now(),
            updated_at=datetime.now(),
            qa_pairs=[],
            approved_plan="",
            plan_revisions=0,
            current_iteration=0,
            iterations=[],
            last_iteration_path="",
            total_cost=0.0
        )
        data = state.to_dict()
        assert data["phase"] == "INTERVIEW"
        assert data["project_name"] == "test"

    def test_deserialization(self):
        data = {
            "phase": "BUILD",
            "project_name": "test",
            "source_idea": "idea",
            "started_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "qa_pairs": [],
            "approved_plan": "plan",
            "plan_revisions": 1,
            "current_iteration": 3,
            "iterations": [],
            "last_iteration_path": "/tmp/test",
            "total_cost": 1.50
        }
        state = BuildState.from_dict(data)
        assert state.phase == BuildPhase.BUILD
        assert state.current_iteration == 3

    def test_round_trip(self):
        """Test serialization and deserialization round-trip."""
        original = BuildState(
            phase=BuildPhase.PLANNING,
            project_name="roundtrip-test",
            source_idea="test idea",
            started_at=datetime.now(),
            updated_at=datetime.now(),
            qa_pairs=[{"question": "Q?", "answer": "A"}],
            approved_plan="# Plan",
            plan_revisions=2,
            current_iteration=5,
            iterations=[],
            last_iteration_path="/path/to/iter",
            total_cost=2.50
        )

        data = original.to_dict()
        restored = BuildState.from_dict(data)

        assert restored.project_name == original.project_name
        assert restored.phase == original.phase
        assert restored.total_cost == original.total_cost


class TestRalphLiteOrchestrator:
    """Integration tests for main orchestrator."""

    def test_initialization(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a config for testing
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(f"build_directory: {tmpdir}")

            orch = RalphLiteOrchestrator(
                "test-project",
                "Build a test tool",
                config_path=str(config_path)
            )
            assert orch.project_name == "test-project"
            assert orch.state.phase == BuildPhase.IDLE

    def test_state_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(f"build_directory: {tmpdir}")

            orch = RalphLiteOrchestrator("test", "idea", config_path=str(config_path))
            orch._save_state()
            assert orch.state_file.exists()

    def test_log_event(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(f"build_directory: {tmpdir}")

            orch = RalphLiteOrchestrator("test", "idea", config_path=str(config_path))
            orch._log_event("TEST EVENT", "Test details")

            assert orch.log_file.exists()
            content = orch.log_file.read_text()
            assert "TEST EVENT" in content
            assert "Test details" in content


if __name__ == "__main__":
    print("Run tests with: python -m pytest tests/test_ralph_lite.py -v")
