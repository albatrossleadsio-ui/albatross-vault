#!/usr/bin/env python3
"""
Interview Generator for Ralph-Lite
Part of Albatross Phase 4 - Core Build

Generates interview questions to gather requirements.
MVP: Template-based with keyword detection.
Future: AI-generated contextual questions.
"""

from typing import List, Dict


class InterviewGenerator:
    """
    Generates interview questions based on source idea.
    MVP: Template-based with keyword detection.
    Future: AI-generated contextual questions.
    """

    # Question templates by domain
    QUESTIONS = {
        "web_scraping": [
            "What specific data fields do you need extracted?",
            "Which websites or data sources should we target?",
            "How often should this scraper run? (once, daily, real-time)",
            "What format for output? (CSV, JSON, database, etc.)",
            "Any login/authentication required for the target sites?"
        ],
        "automation": [
            "What triggers this automation? (schedule, event, manual)",
            "What are the input sources or data inputs?",
            "What actions should happen on success?",
            "What should happen on failure? (retry, alert, stop)",
            "Who or what receives the output or notification?"
        ],
        "data_analysis": [
            "What are the data sources?",
            "What metrics or calculations are needed?",
            "Any visualization requirements? (charts, dashboards)",
            "How often should analysis update?",
            "What export formats are needed? (PDF, Excel, etc.)"
        ],
        "api_integration": [
            "Which external APIs or services to integrate?",
            "What authentication method? (API key, OAuth, etc.)",
            "What data to send/receive?",
            "Rate limits or quotas to respect?",
            "Error handling requirements?"
        ],
        "general": [
            "What problem does this solve?",
            "Who is the primary user?",
            "What are the 3 most important features?",
            "Any hard constraints? (time, budget, tech stack)",
            "How will you know this is successful?"
        ]
    }

    def analyze_idea(self, source_idea: str) -> Dict:
        """
        Analyze idea to determine domain and complexity.

        Returns:
            {
                "domain": str,
                "complexity": "simple" | "medium" | "complex",
                "keywords": list,
                "inferred_intent": str
            }
        """
        idea_lower = source_idea.lower()

        # Domain detection
        if any(k in idea_lower for k in ["scrape", "crawl", "extract", "spider"]):
            domain = "web_scraping"
        elif any(k in idea_lower for k in ["automate", "bot", "cron", "schedule"]):
            domain = "automation"
        elif any(k in idea_lower for k in ["analyze", "dashboard", "visualize", "metrics"]):
            domain = "data_analysis"
        elif any(k in idea_lower for k in ["api", "integrate", "webhook", "connect"]):
            domain = "api_integration"
        else:
            domain = "general"

        # Complexity based on length/description
        word_count = len(idea_lower.split())
        if word_count < 20:
            complexity = "simple"
        elif word_count < 50:
            complexity = "medium"
        else:
            complexity = "complex"

        # Extract keywords (simple)
        keywords = [w for w in ["scrape", "automate", "api", "dashboard", "bot"]
                   if w in idea_lower]

        return {
            "domain": domain,
            "complexity": complexity,
            "keywords": keywords,
            "inferred_intent": f"Build a {domain.replace('_', ' ')} tool"
        }

    def generate_questions(self, source_idea: str) -> List[str]:
        """
        Generate interview questions based on idea.

        Args:
            source_idea: The bookmark/idea text

        Returns:
            List of question strings (3-5 questions)
        """
        analysis = self.analyze_idea(source_idea)
        domain = analysis["domain"]

        # Get questions for domain (or general fallback)
        questions = self.QUESTIONS.get(domain, self.QUESTIONS["general"])

        # Limit to 5 questions
        return questions[:5]

    def should_ask_followup(self, question: str, answer: str) -> bool:
        """
        Determine if follow-up question needed.

        MVP: Always return False (no follow-ups)
        Future: Analyze if answer is vague/needs clarification
        """
        return False

    def summarize_requirements(self, qa_pairs: List[Dict]) -> Dict:
        """
        Convert Q&A list to structured requirements.

        Args:
            qa_pairs: List of {"question": str, "answer": str}

        Returns:
            {
                "original_idea": str,
                "domain": str,
                "requirements": {
                    "data_fields": list,
                    "sources": list,
                    "output_format": str,
                    "frequency": str,
                    "constraints": list
                },
                "open_questions": list
            }
        """
        # Simple extraction based on question keywords
        requirements = {
            "data_fields": [],
            "sources": [],
            "output_format": "",
            "frequency": "",
            "constraints": []
        }

        for pair in qa_pairs:
            q = pair["question"].lower()
            a = pair["answer"]

            if "data fields" in q or "fields" in q:
                requirements["data_fields"] = [f.strip() for f in a.split(",")]
            elif "websites" in q or "sources" in q:
                requirements["sources"] = [s.strip() for s in a.split(",")]
            elif "format" in q:
                requirements["output_format"] = a
            elif "often" in q or "frequency" in q:
                requirements["frequency"] = a
            elif "constraint" in q:
                requirements["constraints"].append(a)

        return {
            "original_idea": qa_pairs[0].get("context", "") if qa_pairs else "",
            "domain": "general",
            "requirements": requirements,
            "open_questions": []  # MVP: none
        }


# Convenience function
def create_interview_generator() -> InterviewGenerator:
    """Factory function."""
    return InterviewGenerator()


if __name__ == "__main__":
    # Test
    gen = InterviewGenerator()

    idea = "Build a scraper for website data"
    analysis = gen.analyze_idea(idea)
    print(f"Analysis: {analysis}")

    questions = gen.generate_questions(idea)
    print(f"Questions: {questions}")
