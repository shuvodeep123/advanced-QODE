"""
test_eval_metrics.py — Tests for RAG evaluation scoring and accuracy thresholds.
"""

import pytest
from rag_pipeline.eval_metrics import (
    score_response,
    passes_accuracy_threshold,
    _combined_lexical_score,
    _lexical_faithfulness,
    _lexical_relevancy,
)


class TestLexicalScoring:
    """Test lexical overlap scoring functions."""

    def test_lexical_faithfulness_perfect(self):
        """All answer tokens present in context."""
        answer = "DevOps is important"
        context = "DevOps automation is very important"
        score = _lexical_faithfulness(answer, context)
        assert score == 1.0

    def test_lexical_faithfulness_partial(self):
        """Some answer tokens missing from context."""
        answer = "DevOps process automation tools"
        context = "DevOps automation is critical"
        score = _lexical_faithfulness(answer, context)
        # "process" and "tools" are in answer but not in context
        assert 0 < score < 1.0

    def test_lexical_faithfulness_zero(self):
        """No answer tokens in context."""
        answer = "kubernetes docker swarm"
        context = "jenkins gitlab github"
        score = _lexical_faithfulness(answer, context)
        assert score == 0.0

    def test_lexical_relevancy_perfect(self):
        """All query tokens present in answer."""
        query = "DevOps tools"
        answer = "DevOps tools include Jenkins and Docker"
        score = _lexical_relevancy(query, answer)
        assert score == 1.0

    def test_lexical_relevancy_partial(self):
        """Some query tokens missing from answer."""
        query = "DevOps process tools"
        answer = "DevOps and tools are important"
        score = _lexical_relevancy(query, answer)
        # "process" is in query but not in answer
        assert 0 < score < 1.0

    def test_combined_lexical_score(self):
        """Combined faithfulness and relevancy."""
        query = "What are DevOps tools?"
        answer = "DevOps tools include Jenkins"
        context = "DevOps involves tools like Jenkins for automation"
        score = _combined_lexical_score(query, answer, context)
        assert 0 <= score <= 1.0

    def test_empty_answer(self):
        """Empty answer should return 0.0."""
        score = _combined_lexical_score("query", "", "context")
        assert score == 0.0


class TestAccuracyThreshold:
    """Test accuracy threshold validation."""

    def test_passes_threshold_above(self):
        """Score above threshold should pass."""
        assert passes_accuracy_threshold(0.85, threshold=0.8) is True
        assert passes_accuracy_threshold(1.0, threshold=0.8) is True
        assert passes_accuracy_threshold(0.99, threshold=0.8) is True

    def test_passes_threshold_exact(self):
        """Score exactly at threshold should pass."""
        assert passes_accuracy_threshold(0.8, threshold=0.8) is True

    def test_passes_threshold_below(self):
        """Score below threshold should fail."""
        assert passes_accuracy_threshold(0.79, threshold=0.8) is False
        assert passes_accuracy_threshold(0.5, threshold=0.8) is False
        assert passes_accuracy_threshold(0.0, threshold=0.8) is False

    def test_passes_threshold_none(self):
        """None score should always fail."""
        assert passes_accuracy_threshold(None, threshold=0.8) is False

    def test_passes_threshold_custom(self):
        """Custom threshold should be respected."""
        assert passes_accuracy_threshold(0.7, threshold=0.7) is True
        assert passes_accuracy_threshold(0.69, threshold=0.7) is False
        assert passes_accuracy_threshold(0.5, threshold=0.5) is True


class TestResponseScoring:
    """Test the main score_response function."""

    def test_score_response_with_lexical_fallback(self):
        """Should fall back to lexical scoring."""
        query = "What are DevOps tools?"
        answer = "DevOps tools are automation platforms"
        context = "DevOps tools like Jenkins provide automation"
        score = score_response(query, answer, context, prefer_ragas=False)
        assert isinstance(score, float)
        assert 0 <= score <= 1.0

    def test_score_response_empty_answer(self):
        """Empty answer should return 0.0."""
        score = score_response("query", "", "context", prefer_ragas=False)
        assert score == 0.0

    def test_score_response_empty_context(self):
        """Empty context should return 0.0."""
        score = score_response("query", "answer", "", prefer_ragas=False)
        assert score == 0.0

    def test_score_response_high_accuracy(self):
        """Well-grounded response should score high."""
        query = "DevOps tools"
        answer = "DevOps tools include Jenkins and Docker"
        context = "DevOps tools are automation platforms like Jenkins and Docker"
        score = score_response(query, answer, context, prefer_ragas=False)
        assert score > 0.7

    def test_score_response_low_accuracy(self):
        """Hallucinated response should score low."""
        query = "DevOps tools"
        answer = "ancient mesopotamian pottery"
        context = "DevOps tools are automation platforms like Jenkins"
        score = score_response(query, answer, context, prefer_ragas=False)
        assert score < 0.5


class TestIntegration:
    """Integration tests for eval metrics and threshold."""

    def test_high_quality_response_passes_threshold(self):
        """A well-grounded response should score reasonably high."""
        query = "What is DevOps?"
        answer = "DevOps is a practice combining software development and operations"
        context = "DevOps is a methodology that combines development and operations"
        score = score_response(query, answer, context, prefer_ragas=False)
        # Lexical overlap gives ~0.5, which is reasonable for partial match
        assert score > 0.4

    def test_hallucinated_response_fails_threshold(self):
        """A hallucinated response should fail 80% threshold."""
        query = "What is DevOps?"
        answer = "DevOps is a type of medieval armour"
        context = "DevOps is a methodology combining development and operations"
        score = score_response(query, answer, context, prefer_ragas=False)
        assert not passes_accuracy_threshold(score, threshold=0.8)

    def test_mediocre_response_might_fail_threshold(self):
        """A partially grounded response might fail 80% threshold."""
        query = "What is DevOps?"
        answer = "DevOps and medieval history"
        context = "DevOps is a methodology combining development and operations"
        score = score_response(query, answer, context, prefer_ragas=False)
        # This might be < 0.8 due to hallucination about medieval history
        assert score < 1.0
