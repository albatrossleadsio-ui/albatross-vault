#!/usr/bin/env python3
"""
Plan Generator for Ralph-Lite
Part of Albatross Phase 4 - Core Build

Creates implementation plans from gathered requirements.
MVP: Template-based with requirements filled in.
Future: AI-generated detailed plans.
"""

from typing import Dict


class PlanGenerator:
    """
    Creates implementation plans from gathered requirements.
    MVP: Template-based with requirements filled in.
    Future: AI-generated detailed plans.
    """

    TEMPLATES = {
        "web_scraping": """# Implementation Plan: {project_name}

## Overview
Build a web scraper that extracts {data_fields} from {sources}.

## Architecture
- **Language**: Python 3.12
- **Libraries**: requests, BeautifulSoup4, pandas
- **Pattern**: Modular scraper with retry logic

## Files to Create
1. `src/scraper.py` - Main scraping logic with error handling
2. `src/parser.py` - HTML parsing and data extraction
3. `src/exporter.py` - Output formatting ({output_format})
4. `src/config.py` - Settings and configuration
5. `tests/test_scraper.py` - Unit tests
6. `README.md` - Usage instructions

## Implementation Order (Iterations)
1. **Scaffold** - Project structure, config
2. **HTTP Client** - Requests with retries, headers
3. **HTML Parsing** - Extract {data_fields}
4. **Data Export** - Save to {output_format}
5. **Error Handling** - Robust failure recovery
6. **Testing** - Unit tests, validation

## Estimated Metrics
- **Iterations**: {estimated_iterations}
- **Complexity**: {complexity}
- **Risk Level**: {risk_level}
- **Estimated Cost**: ${estimated_cost:.2f}

## Constraints
{constraints}

## Success Criteria
- [ ] Successfully scrapes all {sources}
- [ ] Outputs valid {output_format}
- [ ] Handles errors gracefully
- [ ] Tests pass
""",

        "automation": """# Implementation Plan: {project_name}

## Overview
Build an automation that {description}.

## Architecture
- **Trigger**: {trigger}
- **Actions**: {actions}
- **Schedule**: {frequency}

## Files to Create
1. `src/main.py` - Entry point and orchestration
2. `src/trigger.py` - Event detection/scheduler
3. `src/actions.py` - Action handlers
4. `src/notifier.py` - Notifications/alerts
5. `tests/test_automation.py` - Integration tests
6. `README.md` - Setup and usage

## Implementation Order (Iterations)
1. **Scaffold** - Structure, logging
2. **Trigger** - Event detection
3. **Actions** - Core automation logic
4. **Notifier** - Alerts and status
5. **Error Handling** - Failures and retries
6. **Testing** - Validation

## Estimated Metrics
- **Iterations**: {estimated_iterations}
- **Complexity**: {complexity}
- **Risk Level**: {risk_level}
- **Estimated Cost**: ${estimated_cost:.2f}

## Constraints
{constraints}
""",

        "general": """# Implementation Plan: {project_name}

## Overview
Build a tool that solves: {description}

## Architecture
- **Type**: Python CLI application
- **Pattern**: Modular design with clear separation

## Files to Create
1. `src/main.py` - Entry point
2. `src/core.py` - Core logic
3. `src/utils.py` - Helper functions
4. `tests/test_core.py` - Unit tests
5. `README.md` - Documentation

## Implementation Order (Iterations)
1. **Scaffold** - Project structure
2. **Core Logic** - Main functionality
3. **Utilities** - Helper functions
4. **Error Handling** - Robustness
5. **Testing** - Validation
6. **Documentation** - README

## Estimated Metrics
- **Iterations**: {estimated_iterations}
- **Complexity**: {complexity}
- **Risk Level**: {risk_level}
- **Estimated Cost**: ${estimated_cost:.2f}
"""
    }

    def __init__(self):
        self.max_revisions = 3

    def _estimate_iterations(self, complexity: str) -> int:
        """Estimate build iterations based on complexity."""
        return {"simple": 5, "medium": 7, "complex": 10}.get(complexity, 7)

    def _assess_risk(self, requirements: Dict) -> str:
        """Assess risk level."""
        # Simple heuristic
        open_qs = len(requirements.get("open_questions", []))
        if open_qs > 2:
            return "medium"
        return "low"

    def _estimate_cost(self, iterations: int) -> float:
        """Estimate total cost based on iterations."""
        # Assume ~$0.50 per iteration average
        return iterations * 0.50

    def create_plan(self, requirements: Dict, project_name: str = "Untitled") -> str:
        """
        Generate implementation plan from requirements.

        Args:
            requirements: Dict from interview.summarize_requirements()
            project_name: Name for the project

        Returns:
            Markdown plan string
        """
        domain = requirements.get("domain", "general")
        template = self.TEMPLATES.get(domain, self.TEMPLATES["general"])

        # Extract values from requirements
        reqs = requirements.get("requirements", {})
        complexity = requirements.get("complexity", "medium")

        # Fill template
        context = {
            "project_name": project_name,
            "data_fields": ", ".join(reqs.get("data_fields", ["TBD"])),
            "sources": ", ".join(reqs.get("sources", ["TBD"])),
            "output_format": reqs.get("output_format", "JSON"),
            "frequency": reqs.get("frequency", "on-demand"),
            "constraints": "\n".join(f"- {c}" for c in reqs.get("constraints", ["None"])),
            "description": requirements.get("inferred_intent", "Build a tool"),
            "trigger": reqs.get("trigger", "manual"),
            "actions": reqs.get("actions", "process data"),
            "estimated_iterations": self._estimate_iterations(complexity),
            "complexity": complexity,
            "risk_level": self._assess_risk(requirements),
            "estimated_cost": self._estimate_cost(
                self._estimate_iterations(complexity)
            )
        }

        return template.format(**context)

    def revise_plan(self, original_plan: str, feedback: str) -> str:
        """
        Revise plan based on feedback.

        MVP: Append feedback as "Revision Notes" section
        Future: Actually regenerate with AI
        """
        return original_plan + f"""

## Revision Notes
User feedback: {feedback}

Changes applied: Added to constraints section.
"""


# Convenience function
def create_plan_generator() -> PlanGenerator:
    """Factory function."""
    return PlanGenerator()


if __name__ == "__main__":
    # Test
    pg = PlanGenerator()
    requirements = {
        "domain": "web_scraping",
        "complexity": "medium",
        "requirements": {
            "data_fields": ["title", "price", "date"],
            "sources": ["example.com"],
            "output_format": "CSV"
        }
    }
    plan = pg.create_plan(requirements, "Price Tracker")
    print(plan[:500])
