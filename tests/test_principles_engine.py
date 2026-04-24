"""
tests/test_principles_engine.py — Unit tests for principles_engine.py.

Tests the 9-principle × 3-discipline extraction and enrichment logic.
Zero external dependencies.
"""

from __future__ import annotations

import pytest
from rag_pipeline.principles_engine import (
    PrinciplesEngine,
    extract_principle_context,
    PRINCIPLES,
)


# ---------------------------------------------------------------------------
# PRINCIPLES data integrity
# ---------------------------------------------------------------------------

class TestPrinciplesData:
    def test_nine_principles_defined(self):
        assert len(PRINCIPLES) == 9

    def test_each_principle_has_required_keys(self):
        required = {"id", "name", "number", "keywords", "enrichment"}
        for p in PRINCIPLES:
            assert required.issubset(p.keys()), f"Missing keys in principle: {p['name']}"

    def test_enrichment_has_three_disciplines(self):
        disciplines = {"People", "Process", "Technology"}
        for p in PRINCIPLES:
            assert disciplines.issubset(p["enrichment"].keys()), (
                f"Missing discipline in principle: {p['name']}"
            )

    def test_principles_numbered_1_to_9(self):
        numbers = sorted(p["number"] for p in PRINCIPLES)
        assert numbers == list(range(1, 10))

    def test_all_enrichments_non_empty(self):
        for p in PRINCIPLES:
            for disc, text in p["enrichment"].items():
                assert text.strip(), (
                    f"Empty enrichment for {p['name']} / {disc}"
                )


# ---------------------------------------------------------------------------
# PrinciplesEngine.match_principle
# ---------------------------------------------------------------------------

class TestMatchPrinciple:
    def setup_method(self):
        self.engine = PrinciplesEngine()

    def test_security_keyword_matches_security(self):
        result = self.engine.match_principle("How can I improve security scanning?")
        assert result is not None
        assert result["id"] == "security"

    def test_reliability_keyword(self):
        result = self.engine.match_principle("We need better disaster recovery and failover")
        assert result is not None
        assert result["id"] == "reliability"

    def test_requirement_engineering(self):
        result = self.engine.match_principle("Backlog grooming and user story creation")
        assert result is not None
        assert result["id"] == "req_engg"

    def test_build_release(self):
        result = self.engine.match_principle("How do I improve the CI/CD pipeline build?")
        assert result is not None
        assert result["id"] == "build_release_engg"

    def test_quality_engineering(self):
        result = self.engine.match_principle("We need more unit test coverage and QA automation")
        assert result is not None
        assert result["id"] == "quality_engg"

    def test_ontology_engineering(self):
        result = self.engine.match_principle("Build a knowledge graph with entity relationships")
        assert result is not None
        assert result["id"] == "ontology_engg"

    def test_no_match_returns_none(self):
        result = self.engine.match_principle("Hello, what is the weather today?")
        assert result is None

    def test_case_insensitive(self):
        result = self.engine.match_principle("SECURITY VULNERABILITY SAST DAST")
        assert result is not None
        assert result["id"] == "security"


# ---------------------------------------------------------------------------
# PrinciplesEngine.match_discipline
# ---------------------------------------------------------------------------

class TestMatchDiscipline:
    def setup_method(self):
        self.engine = PrinciplesEngine()

    def test_people_discipline(self):
        assert self.engine.match_discipline("Which team role owns this activity?") == "People"

    def test_process_discipline(self):
        assert self.engine.match_discipline("What is the workflow and SDLC procedure?") == "Process"

    def test_technology_discipline(self):
        assert self.engine.match_discipline("Which tool or platform should we use?") == "Technology"

    def test_default_to_technology(self):
        # No discipline keywords → defaults to Technology
        assert self.engine.match_discipline("general question") == "Technology"

    def test_people_beats_technology_by_score(self):
        # More people keywords
        assert self.engine.match_discipline("team role stakeholder people person") == "People"


# ---------------------------------------------------------------------------
# PrinciplesEngine.get_enrichment
# ---------------------------------------------------------------------------

class TestGetEnrichment:
    def setup_method(self):
        self.engine = PrinciplesEngine()

    def test_security_people_enrichment(self):
        text = self.engine.get_enrichment("Security", "People")
        assert "security champion" in text.lower() or "developer" in text.lower()

    def test_reliability_technology_enrichment(self):
        text = self.engine.get_enrichment("Reliability", "Technology")
        assert len(text) > 10

    def test_unknown_principle_returns_empty(self):
        assert self.engine.get_enrichment("Unknown Principle", "People") == ""

    def test_none_principle_returns_empty(self):
        assert self.engine.get_enrichment(None, "Process") == ""


# ---------------------------------------------------------------------------
# extract_principle_context (top-level convenience function)
# ---------------------------------------------------------------------------

class TestExtractPrincipleContext:
    def test_returns_dict_with_required_keys(self):
        ctx = extract_principle_context("Improve security for our technology stack")
        assert "principle" in ctx
        assert "discipline" in ctx
        assert "enrichment" in ctx

    def test_security_technology_extraction(self):
        ctx = extract_principle_context("How can I improve SAST security scanning in our CI/CD tool?")
        assert ctx["principle"] == "Security"
        assert ctx["discipline"] == "Technology"
        assert len(ctx["enrichment"]) > 0

    def test_no_match_returns_none_principle(self):
        ctx = extract_principle_context("Tell me a joke")
        assert ctx["principle"] is None
        assert ctx["enrichment"] == ""

    def test_enrichment_matches_discipline(self):
        ctx = extract_principle_context(
            "What team roles are responsible for reliability and failover?"
        )
        # reliability + people keywords
        assert ctx["principle"] == "Reliability"
        assert ctx["discipline"] == "People"
        assert "sre" in ctx["enrichment"].lower() or "reliability" in ctx["enrichment"].lower()

    def test_environment_engineering_process(self):
        ctx = extract_principle_context(
            "How can we improve our Terraform IaC provisioning workflow and procedure?"
        )
        assert ctx["principle"] == "Environment Engineering"
        assert ctx["discipline"] == "Process"
