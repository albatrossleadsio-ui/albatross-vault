#!/usr/bin/env python3
"""
Ralph-Lite Orchestrator
Main controller for autonomous builds with human checkpoints.

Part of Albatross Phase 4 Core Build.
"""

import os
import sys
import json
import yaml
import logging
from datetime import datetime
from pathlib import Path
from enum import Enum, auto
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.telegram import (
    send_message, request_user_input, parse_command,
    send_iteration_result, send_plan_for_approval,
    send_interview_question, send_build_complete,
    send_alert
)
from src.utils.token_tracker import TokenGuardian, BudgetExceeded
from src.core.interview import InterviewGenerator
from src.core.planner import PlanGenerator
from src.core.builder import IterationBuilder, IterationResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BuildPhase(Enum):
    """Enumeration of build phases."""
    IDLE = auto()
    INTERVIEW = auto()
    PLANNING = auto()
    BUILD = auto()
    DONE = auto()
    PAUSED = auto()
    FAILED = auto()


@dataclass
class BuildState:
    """Persistent state for a build."""
    phase: BuildPhase
    project_name: str
    source_idea: str
    started_at: datetime
    updated_at: datetime

    # Interview phase data
    qa_pairs: List[Dict]

    # Planning phase data
    approved_plan: str
    plan_revisions: int

    # Build phase data
    current_iteration: int
    iterations: List[IterationResult]
    last_iteration_path: str

    # Financial tracking
    total_cost: float

    # Pause/resume
    paused_at: Optional[datetime] = None
    pause_reason: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'phase': self.phase.name,
            'project_name': self.project_name,
            'source_idea': self.source_idea,
            'started_at': self.started_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'qa_pairs': self.qa_pairs,
            'approved_plan': self.approved_plan,
            'plan_revisions': self.plan_revisions,
            'current_iteration': self.current_iteration,
            'iterations': [self._iteration_to_dict(i) for i in self.iterations],
            'last_iteration_path': self.last_iteration_path,
            'total_cost': self.total_cost,
            'paused_at': self.paused_at.isoformat() if self.paused_at else None,
            'pause_reason': self.pause_reason
        }

    @staticmethod
    def _iteration_to_dict(iter_result: IterationResult) -> Dict:
        """Convert IterationResult to dict."""
        return {
            'success': iter_result.success,
            'iteration_num': iter_result.iteration_num,
            'files_created': iter_result.files_created,
            'files_modified': iter_result.files_modified,
            'tests_passed': iter_result.tests_passed,
            'cost': iter_result.cost,
            'path': iter_result.path,
            'summary': iter_result.summary
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'BuildState':
        """Create BuildState from dictionary."""
        # Convert phase name back to enum
        phase = BuildPhase[data.get('phase', 'IDLE')]

        # Parse dates
        started_at = datetime.fromisoformat(data['started_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        paused_at = datetime.fromisoformat(data['paused_at']) if data.get('paused_at') else None

        # Reconstruct IterationResults
        iterations = []
        for iter_data in data.get('iterations', []):
            iterations.append(IterationResult(
                success=iter_data['success'],
                iteration_num=iter_data['iteration_num'],
                files_created=iter_data['files_created'],
                files_modified=iter_data['files_modified'],
                tests_passed=iter_data['tests_passed'],
                cost=iter_data['cost'],
                path=iter_data['path'],
                summary=iter_data['summary']
            ))

        return cls(
            phase=phase,
            project_name=data['project_name'],
            source_idea=data['source_idea'],
            started_at=started_at,
            updated_at=updated_at,
            qa_pairs=data.get('qa_pairs', []),
            approved_plan=data.get('approved_plan', ''),
            plan_revisions=data.get('plan_revisions', 0),
            current_iteration=data.get('current_iteration', 0),
            iterations=iterations,
            last_iteration_path=data.get('last_iteration_path', ''),
            total_cost=data.get('total_cost', 0.0),
            paused_at=paused_at,
            pause_reason=data.get('pause_reason')
        )


class RalphLiteOrchestrator:
    """
    Main orchestrator for Ralph-Lite autonomous builds.

    Manages 4-phase workflow with human checkpoints:
    1. INTERVIEW - Gather requirements via Q&A
    2. PLANNING - Create and approve implementation plan
    3. BUILD - Iterative development with per-iteration approval
    4. DONE - Finalize and deliver

    State is persisted to filesystem for resume capability.
    """

    def __init__(self, project_name: str, source_idea: str,
                 max_iterations: int = 10, config_path: Optional[str] = None):
        """
        Initialize Ralph-Lite orchestrator.

        Args:
            project_name: Unique project identifier
            source_idea: The original bookmark/idea text
            max_iterations: Hard stop for build phase (default 10)
            config_path: Path to YAML config (optional)
        """
        self.project_name = project_name
        self.source_idea = source_idea
        self.max_iterations = max_iterations

        # Load config
        self.config = self._load_config(config_path)

        # Setup paths
        self.build_base = Path(self.config.get('build_directory',
                                              '~/albatross-builds')).expanduser()
        self.build_dir = self.build_base / f"{datetime.now().strftime('%Y-%m-%d')}-{project_name}"
        self.build_dir.mkdir(parents=True, exist_ok=True)

        self.state_file = self.build_dir / "BUILD_STATE.json"
        self.log_file = self.build_dir / "RALPH_LITE_LOG.md"
        self.cost_file = self.build_dir / "COST_TRACKING.json"

        # Initialize components
        self.guardian = TokenGuardian(
            daily_limit=self.config.get('max_daily_cost', 5.00)
        )
        self.interview_gen = InterviewGenerator()
        self.planner = PlanGenerator()
        self.builder: Optional[IterationBuilder] = None

        # Initialize or load state
        self.state = self._init_or_load_state()

        logger.info(f"Ralph-Lite initialized: {project_name}")
        logger.info(f"Build directory: {self.build_dir}")

    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load YAML configuration."""
        if config_path:
            path = Path(config_path)
        else:
            path = Path("~/albatross/config/ralph_lite.yaml").expanduser()

        if path.exists():
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        return {}

    def _init_or_load_state(self) -> BuildState:
        """Initialize new state or load existing for resume."""
        if self.state_file.exists():
            logger.info("Resuming from existing state")
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            return BuildState.from_dict(data)

        # New build
        now = datetime.now()
        return BuildState(
            phase=BuildPhase.IDLE,
            project_name=self.project_name,
            source_idea=self.source_idea,
            started_at=now,
            updated_at=now,
            qa_pairs=[],
            approved_plan='',
            plan_revisions=0,
            current_iteration=0,
            iterations=[],
            last_iteration_path='',
            total_cost=0.0
        )

    def _save_state(self):
        """Persist state to filesystem."""
        self.state.updated_at = datetime.now()
        with open(self.state_file, 'w') as f:
            json.dump(self.state.to_dict(), f, indent=2)
        logger.debug("State saved")

    def _log_event(self, event: str, details: str = ""):
        """Log event to human-readable transcript."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        entry = f"\n## [{timestamp}] {event}\n{details}\n"

        with open(self.log_file, 'a') as f:
            f.write(entry)

    def _check_budget(self, estimated_cost: float = 0.0) -> bool:
        """Check if we have budget remaining."""
        if not self.guardian.check_budget(estimated_cost):
            self._pause_build("Budget limit reached",
                            f"Daily limit ${self.guardian.daily_limit} reached")
            return False
        return True

    def _pause_build(self, reason: str, details: str):
        """Pause build with reason."""
        self.state.phase = BuildPhase.PAUSED
        self.state.paused_at = datetime.now()
        self.state.pause_reason = reason
        self._save_state()

        self._log_event("BUILD PAUSED", f"{reason}: {details}")
        send_alert("Build Paused", f"{reason}\n\n{details}", "warning")

        logger.warning(f"Build paused: {reason}")

    def _ask_question(self, question: str) -> str:
        """Wrapper for asking question via Telegram."""
        q_num = len(self.state.qa_pairs) + 1
        total = self.config.get('phases', {}).get('interview', {}).get('max_questions', 5)

        try:
            answer = send_interview_question(q_num, total, question)
            self.state.qa_pairs.append({
                'question': question,
                'answer': answer,
                'timestamp': datetime.now().isoformat()
            })
            self._save_state()
            return answer
        except Exception as e:
            self._pause_build("Interview timeout", str(e))
            raise

    def _request_approval(self, content: str, estimated_cost: float) -> Tuple[bool, str]:
        """Request human approval for plan."""
        try:
            command = send_plan_for_approval(content, estimated_cost)
            parsed = parse_command(command)

            if parsed['action'] == 'APPROVE':
                return True, ""
            elif parsed['action'] == 'REJECT':
                return False, "rejected"
            elif parsed['action'] == 'REVISE':
                return False, parsed.get('parameter', 'needs revision')
            else:
                # Unknown command, treat as revise
                return False, f"unclear command: {command}"

        except Exception as e:
            self._pause_build("Approval timeout", str(e))
            raise

    def _checkpoint_iteration(self, iteration: IterationResult) -> str:
        """Checkpoint after iteration, get human command."""
        try:
            command = send_iteration_result(
                iteration.iteration_num,
                self.max_iterations,
                iteration.files_created + iteration.files_modified,
                "Tests: passing" if iteration.tests_passed else "Tests: failing",
                iteration.cost
            )
            return command

        except Exception as e:
            self._pause_build("Checkpoint timeout", str(e))
            raise

    # =================================================================
    # PHASE METHODS
    # =================================================================

    def _run_interview_phase(self) -> Dict:
        """
        Phase 1: Interview - Gather requirements via Q&A.

        Returns:
            Requirements dictionary
        """
        logger.info("Starting Phase 1: Interview")
        self.state.phase = BuildPhase.INTERVIEW
        self._save_state()

        self._log_event("PHASE 1 START", "Interview phase")
        send_message(f"Starting build: <b>{self.project_name}</b>\n\nPhase 1: Interview")

        # Generate questions
        questions = self.interview_gen.generate_questions(self.source_idea)

        for question in questions:
            # Check budget (low cost for interview)
            if not self._check_budget(0.10):
                raise BudgetExceeded("Budget exhausted during interview")

            # Ask and store answer
            answer = self._ask_question(question)
            self._log_event("Question answered", f"Q: {question}\nA: {answer}")

            # Small cost for "processing"
            self.guardian.log_cost("interview_question", "interview",
                                  len(self.state.qa_pairs), 0.05,
                                  self.project_name)
            self.state.total_cost += 0.05
            self._save_state()

        # Summarize requirements
        requirements = self.interview_gen.summarize_requirements(self.state.qa_pairs)
        requirements['project_name'] = self.project_name

        self._log_event("Phase 1 Complete", f"Requirements gathered: {requirements}")
        return requirements

    def _run_planning_phase(self, requirements: Dict) -> str:
        """
        Phase 2: Planning - Create and approve implementation plan.

        Returns:
            Approved plan markdown
        """
        logger.info("Starting Phase 2: Planning")
        self.state.phase = BuildPhase.PLANNING
        self._save_state()

        self._log_event("PHASE 2 START", "Planning phase")

        max_revisions = self.config.get('phases', {}).get('planning', {}).get('max_revisions', 3)

        for attempt in range(max_revisions):
            # Check budget
            if not self._check_budget(0.30):
                raise BudgetExceeded("Budget exhausted during planning")

            # Generate plan
            plan = self.planner.create_plan(requirements, self.project_name)

            # Estimate cost based on iterations
            estimated_cost = 7 * 0.50  # Default 7 iterations @ $0.50

            # Request approval
            approved, feedback = self._request_approval(plan, estimated_cost)

            if approved:
                self.state.approved_plan = plan
                self._save_state()
                self._log_event("Plan approved", f"Revisions: {self.state.plan_revisions}")

                # Save plan to file
                plan_file = self.build_dir / "IMPLEMENTATION_PLAN.md"
                plan_file.write_text(plan)

                self.guardian.log_cost("plan_approved", "planning", 0, 0.30, self.project_name)
                self.state.total_cost += 0.30

                return plan

            # Not approved, revise
            self.state.plan_revisions += 1
            if feedback == "rejected":
                raise RuntimeError("Plan rejected by user")

            self._log_event("Plan revision requested", feedback)
            send_message(f"Revising plan (attempt {self.state.plan_revisions + 1})...")

        raise RuntimeError(f"Max revisions ({max_revisions}) exceeded")

    def _run_build_phase(self, plan: str) -> bool:
        """
        Phase 3: Build - Iterative development with checkpoints.

        Returns:
            True if build completed, False if stopped early
        """
        logger.info("Starting Phase 3: Build")
        self.state.phase = BuildPhase.BUILD
        self._save_state()

        self._log_event("PHASE 3 START", "Build phase")

        # Initialize builder
        self.builder = IterationBuilder(str(self.build_dir))

        # Parse plan for iterations (simple: 7 iterations)
        # Future: Parse IMPLEMENTATION_PLAN.md for actual iteration list
        iterations = [
            "Create scaffold and project structure",
            "Implement core functionality",
            "Add error handling and validation",
            "Implement data processing",
            "Add output/formatting",
            "Create tests",
            "Final polish and documentation"
        ][:self.max_iterations]

        # Iteration 0: Scaffold
        if self.state.current_iteration == 0:
            if not self._check_budget(0.10):
                raise BudgetExceeded("Budget exhausted")

            result = self.builder.create_scaffold(plan, {})
            self.state.iterations.append(result)
            self.state.last_iteration_path = result.path
            self.state.current_iteration = 0
            self._save_state()

            self.guardian.log_cost("scaffold", "build", 0, 0.10, self.project_name)
            self.state.total_cost += 0.10

        # Iterations 1-N
        for i in range(1, len(iterations) + 1):
            if self.state.current_iteration >= i:
                logger.info(f"Skipping iteration {i}, already done")
                continue

            # Check budget
            if not self._check_budget(0.50):
                raise BudgetExceeded("Budget exhausted during build")

            # Get task
            task = iterations[i-1]

            # Build iteration
            result = self.builder.build_iteration(
                i, task, self.state.last_iteration_path
            )

            self.state.iterations.append(result)
            self.state.last_iteration_path = result.path
            self.state.current_iteration = i
            self._save_state()

            # Log cost
            self.guardian.log_cost(f"build_iter_{i}", "build", i, result.cost,
                                  self.project_name)
            self.state.total_cost += result.cost

            # Checkpoint: Get human command
            command = self._checkpoint_iteration(result)
            parsed = parse_command(command)

            if parsed['action'] == 'STOP':
                self._log_event("Build stopped by user", f"At iteration {i}")
                return False

            elif parsed['action'] == 'FIX':
                # Implement fix (placeholder)
                fix_desc = parsed.get('parameter', 'general fix')
                self._log_event("Fix requested", fix_desc)
                send_message(f"Applying fix: {fix_desc}...")
                # In full version, would regenerate with fix
                # For MVP, just log it

            elif parsed['action'].startswith('ROLLBACK'):
                # Rollback to previous iteration
                target = int(parsed.get('parameter', i-1))
                self._log_event("Rollback requested", f"To iteration {target}")
                if target < len(self.state.iterations):
                    self.state.current_iteration = target
                    self.state.last_iteration_path = self.state.iterations[target].path
                    self._save_state()
                    send_message(f"Rolled back to iteration {target}")
                continue  # Redo from target iteration

            # CONTINUE or FIX applied - proceed to next iteration

        return True

    def _run_done_phase(self) -> bool:
        """
        Phase 4: Done - Finalize build.

        Returns:
            True on success
        """
        logger.info("Starting Phase 4: Done")
        self.state.phase = BuildPhase.DONE
        self._save_state()

        self._log_event("PHASE 4 START", "Finalization")

        # Create FINAL directory
        final = self.builder.create_final(self.state.last_iteration_path)

        # Send completion notification
        send_build_complete(
            final['path'],
            self.state.total_cost,
            self.state.current_iteration,
            final['files']
        )

        self._log_event("BUILD COMPLETE",
                       f"Total cost: ${self.state.total_cost:.2f}, "
                       f"Iterations: {self.state.current_iteration}")

        self._save_state()
        return True

    # =================================================================
    # PUBLIC API
    # =================================================================

    def run(self) -> Dict:
        """
        Execute full Ralph-Lite workflow.

        Returns:
            Dict with build result summary
        """
        try:
            # Phase 1: Interview
            requirements = self._run_interview_phase()

            # Phase 2: Planning
            plan = self._run_planning_phase(requirements)

            # Phase 3: Build
            completed = self._run_build_phase(plan)

            # Phase 4: Done
            if completed:
                self._run_done_phase()

            return {
                'success': True,
                'project_path': str(self.build_dir),
                'final_path': str(self.build_dir / "FINAL"),
                'total_cost': self.state.total_cost,
                'iterations': self.state.current_iteration,
                'phase': self.state.phase.name
            }

        except BudgetExceeded as e:
            logger.error(f"Budget exceeded: {e}")
            self._pause_build("Budget limit", str(e))
            return {
                'success': False,
                'reason': 'budget_exceeded',
                'project_path': str(self.build_dir),
                'total_cost': self.state.total_cost
            }

        except Exception as e:
            logger.error(f"Build failed: {e}")
            self.state.phase = BuildPhase.FAILED
            self._save_state()
            return {
                'success': False,
                'reason': 'error',
                'error': str(e),
                'project_path': str(self.build_dir)
            }

    @classmethod
    def resume(cls, build_dir: str) -> Dict:
        """
        Resume a paused build from directory.

        Args:
            build_dir: Path to build directory with BUILD_STATE.json

        Returns:
            Build result
        """
        state_file = Path(build_dir) / "BUILD_STATE.json"
        if not state_file.exists():
            raise FileNotFoundError(f"No state file found in {build_dir}")

        with open(state_file, 'r') as f:
            data = json.load(f)

        state = BuildState.from_dict(data)

        # Create orchestrator with loaded state
        orchestrator = cls(
            project_name=state.project_name,
            source_idea=state.source_idea
        )
        orchestrator.state = state
        orchestrator.build_dir = Path(build_dir)

        # Resume from current phase
        send_message(f"Resuming build: <b>{state.project_name}</b>\n"
                    f"Phase: {state.phase.name}")

        # Continue based on phase
        if state.phase == BuildPhase.INTERVIEW:
            # Need to restart interview from where we left off
            # For MVP, restart phase
            requirements = orchestrator._run_interview_phase()
            plan = orchestrator._run_planning_phase(requirements)
            completed = orchestrator._run_build_phase(plan)
            if completed:
                orchestrator._run_done_phase()

        elif state.phase == BuildPhase.PLANNING:
            requirements = orchestrator.interview_gen.summarize_requirements(state.qa_pairs)
            plan = orchestrator._run_planning_phase(requirements)
            completed = orchestrator._run_build_phase(plan)
            if completed:
                orchestrator._run_done_phase()

        elif state.phase == BuildPhase.BUILD:
            completed = orchestrator._run_build_phase(state.approved_plan)
            if completed:
                orchestrator._run_done_phase()

        elif state.phase == BuildPhase.PAUSED:
            send_message("Build was paused. Use run() to continue from checkpoint.")
            return {
                'success': False,
                'reason': 'paused',
                'project_path': build_dir
            }

        return {
            'success': orchestrator.state.phase == BuildPhase.DONE,
            'project_path': build_dir,
            'total_cost': orchestrator.state.total_cost
        }


# Convenience function
def quick_build(project_name: str, idea: str) -> Dict:
    """Quick entry point for simple builds."""
    orchestrator = RalphLiteOrchestrator(project_name, idea)
    return orchestrator.run()


if __name__ == "__main__":
    # Simple test
    print("Ralph-Lite Orchestrator")
    print("Use: from src.core.ralph_lite import RalphLiteOrchestrator")
    print("     orch = RalphLiteOrchestrator('my-project', 'Build a scraper')")
    print("     result = orch.run()")
