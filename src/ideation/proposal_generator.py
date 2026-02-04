#!/usr/bin/env python3
"""
Proposal Generator for Albatross Ideation Engine
Part of Albatross Phase 4 - Ideation

Create BUILD/REJECT proposals from analysis.
"""

from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime

from .tweet_analyzer import TweetAnalysis
from .deep_researcher import ResearchResult
from .opportunity_matcher import PatternMatch


@dataclass
class Proposal:
    """Build proposal for user approval."""
    bookmark_id: str
    title: str
    overview: str
    market_validation: str
    technical_approach: str
    estimated_metrics: Dict
    reusable_components: List[str]
    differentiator: str
    risks: List[str]
    recommendation: str  # "BUILD", "RESEARCH_MORE", "REJECT"
    confidence_score: int  # 1-10


class ProposalGenerator:
    """
    Generate BUILD proposals from analyzed opportunities.
    """

    def generate(self, bookmark_id: str, tweet_analysis: TweetAnalysis,
                 research: ResearchResult, matches: List[PatternMatch]) -> Proposal:
        """
        Generate proposal from analysis components.

        Args:
            bookmark_id: ID of source bookmark
            tweet_analysis: From TweetAnalyzer
            research: From DeepResearcher
            matches: From OpportunityMatcher

        Returns:
            Proposal ready for Section 2
        """
        # Determine recommendation
        confidence = self._calculate_confidence(tweet_analysis, research, matches)
        recommendation = self._determine_recommendation(confidence, research.risks)

        # Generate title
        title = self._generate_title(tweet_analysis)

        # Build components list
        components = []
        for match in matches[:2]:  # Top 2 matches
            components.extend(match.reusable_components)
        components = list(set(components))  # Deduplicate

        # Estimate metrics
        if matches:
            best_match = matches[0]
            avg_iterations = best_match.similarity_score
            estimated_cost = avg_iterations * 0.50
        else:
            avg_iterations = 7
            estimated_cost = 3.50

        return Proposal(
            bookmark_id=bookmark_id,
            title=title,
            overview=self._generate_overview(tweet_analysis),
            market_validation=self._generate_market_validation(research),
            technical_approach=self._generate_technical_approach(
                tweet_analysis, matches
            ),
            estimated_metrics={
                'iterations': avg_iterations,
                'cost': estimated_cost,
                'time': f"{avg_iterations * 20} minutes"
            },
            reusable_components=components,
            differentiator=research.differentiator,
            risks=research.risks[:3],  # Top 3 risks
            recommendation=recommendation,
            confidence_score=confidence
        )

    def format_for_telegram(self, proposal: Proposal) -> str:
        """Format proposal as Telegram message."""
        components_str = '\n'.join(f"  - {c}" for c in proposal.reusable_components) if proposal.reusable_components else "  - None (new build)"
        risks_str = '\n'.join(f"  - {r}" for r in proposal.risks)

        return f"""<b>PROPOSAL: {proposal.title}</b>
{'=' * 35}

<b>Overview:</b>
{proposal.overview}

<b>Market Validation:</b>
{proposal.market_validation}

<b>Technical Approach:</b>
{proposal.technical_approach}

<b>Estimated:</b>
  - Iterations: {proposal.estimated_metrics['iterations']}
  - Cost: ${proposal.estimated_metrics['cost']:.2f}
  - Time: {proposal.estimated_metrics['time']}

<b>Reusable Components:</b>
{components_str}

<b>Differentiator:</b>
{proposal.differentiator}

<b>Risks:</b>
{risks_str}

<b>Confidence:</b> {proposal.confidence_score}/10
<b>Recommendation:</b> {proposal.recommendation}

<b>YOUR DECISION:</b>
[BUILD IT] [RESEARCH MORE] [REJECT]
"""

    def format_for_markdown(self, proposal: Proposal) -> str:
        """Format proposal as Markdown for Google Docs/files."""
        components_str = '\n'.join(f"- {c}" for c in proposal.reusable_components) if proposal.reusable_components else "- None (new build)"
        risks_str = '\n'.join(f"- {r}" for r in proposal.risks)

        return f"""# Proposal: {proposal.title}

## Overview
{proposal.overview}

## Market Validation
{proposal.market_validation}

## Technical Approach
{proposal.technical_approach}

## Estimates
- **Iterations:** {proposal.estimated_metrics['iterations']}
- **Cost:** ${proposal.estimated_metrics['cost']:.2f}
- **Time:** {proposal.estimated_metrics['time']}

## Reusable Components
{components_str}

## Differentiator
{proposal.differentiator}

## Risks
{risks_str}

## Confidence: {proposal.confidence_score}/10
## Recommendation: **{proposal.recommendation}**

---
*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""

    def _calculate_confidence(self, tweet: TweetAnalysis,
                             research: ResearchResult,
                             matches: List[PatternMatch]) -> int:
        """Calculate confidence score."""
        score = 5  # Base

        # Has metrics (revenue, time)
        if tweet.metrics:
            score += 2

        # Market validation
        if research.competitors:
            score += 1

        # Pattern match
        if matches and matches[0].similarity_score >= 7:
            score += 2

        # Feasibility
        if research.technical_feasibility == 'high':
            score += 1

        return min(score, 10)

    def _determine_recommendation(self, confidence: int,
                                   risks: List[str]) -> str:
        """Determine recommendation."""
        if confidence >= 8:
            return "BUILD"
        elif confidence >= 5:
            return "RESEARCH_MORE"
        else:
            return "REJECT"

    def _generate_title(self, tweet: TweetAnalysis) -> str:
        """Generate project title."""
        # Extract key concept from first claim or text
        if tweet.key_claims:
            words = tweet.key_claims[0].split()[:6]
        else:
            words = tweet.original_text.split()[:6]

        title = ' '.join(words)
        if len(title) > 40:
            title = title[:37] + "..."

        return f"{title} Tool"

    def _generate_overview(self, tweet: TweetAnalysis) -> str:
        """Generate overview paragraph."""
        domain_name = tweet.suggested_domain.replace('_', ' ')
        claim = tweet.key_claims[0] if tweet.key_claims else 'the bookmarked concept'

        return f"Build a {domain_name} tool based on: {claim}"

    def _generate_market_validation(self, research: ResearchResult) -> str:
        """Generate market section."""
        comps = ", ".join([c['name'] for c in research.competitors[:3]])
        return f"{research.market_size}. Competitors: {comps}. Price point: {research.price_point}."

    def _generate_technical_approach(self, tweet: TweetAnalysis,
                                      matches: List[PatternMatch]) -> str:
        """Generate technical approach."""
        tech_stack = ', '.join(tweet.technology_mentions[:3]) if tweet.technology_mentions else 'Python'

        if matches:
            return f"Adapt {matches[0].pattern_name} pattern. Use {tech_stack}."
        return f"Build from scratch with {tech_stack}."


# Convenience function
def create_proposal(bookmark_id: str, tweet_analysis: TweetAnalysis,
                   research: ResearchResult,
                   matches: List[PatternMatch]) -> str:
    """Generate and format proposal for Telegram."""
    generator = ProposalGenerator()
    proposal = generator.generate(bookmark_id, tweet_analysis, research, matches)
    return generator.format_for_telegram(proposal)


def create_proposal_object(bookmark_id: str, tweet_analysis: TweetAnalysis,
                          research: ResearchResult,
                          matches: List[PatternMatch]) -> Proposal:
    """Generate proposal object (for programmatic use)."""
    generator = ProposalGenerator()
    return generator.generate(bookmark_id, tweet_analysis, research, matches)


if __name__ == "__main__":
    # Test
    from .tweet_analyzer import analyze_tweet
    from .deep_researcher import do_research
    from .opportunity_matcher import find_matches

    text = "Made $50K scraping county assessor data for real estate investors. Built in 3 weeks with Python."

    analysis = analyze_tweet(text)
    research = do_research(analysis.suggested_domain, text)
    matches = find_matches(
        analysis.suggested_domain,
        analysis.technology_mentions,
        analysis.market_indicators,
        text
    )

    proposal_text = create_proposal("test_123", analysis, research, matches)
    print(proposal_text)
