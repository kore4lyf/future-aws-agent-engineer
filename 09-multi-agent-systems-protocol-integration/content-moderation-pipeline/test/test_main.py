
"""
Unit tests for content-moderation-pipeline.
Tests core logic without requiring AWS credentials.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from main import (
    POSTS, HARMFUL_KEYWORDS, BORDERLINE_KEYWORDS,
    DEEP_REVIEW_VERDICTS, NOTICE_TEMPLATES,
    screening_cache, review_cache, notice_cache,
)


class TestDataStructures:
    """Test the data structures and constants."""

    def test_posts_have_unique_ids(self):
        """All posts should have unique IDs."""
        ids = [post["id"] for post in POSTS]
        assert len(ids) == len(set(ids))

    def test_posts_have_text(self):
        """All posts should have non-empty text."""
        for post in POSTS:
            assert "id" in post
            assert "text" in post
            assert isinstance(post["text"], str) and len(post["text"]) > 0

    def test_posts_count(self):
        """Should have 9 test posts."""
        assert len(POSTS) == 9

    def test_harmful_keywords_not_empty(self):
        """Harmful keywords list should not be empty."""
        assert len(HARMFUL_KEYWORDS) > 0

    def test_deep_review_verdicts_structure(self):
        """Each deep review verdict should have required fields."""
        for post_id, data in DEEP_REVIEW_VERDICTS.items():
            assert "verdict" in data
            assert data["verdict"] in ("safe", "harmful")
            assert "reason" in data
            assert isinstance(data["reason"], str) and len(data["reason"]) > 0


class TestKeywordDetection:
    """Test keyword-based content classification."""

    def _contains_harmful(self, text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in HARMFUL_KEYWORDS)

    def _contains_borderline(self, text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in BORDERLINE_KEYWORDS)

    def test_post_004_is_harmful(self):
        post = next(p for p in POSTS if p["id"] == "POST-004")
        assert self._contains_harmful(post["text"])

    def test_post_005_is_harmful(self):
        post = next(p for p in POSTS if p["id"] == "POST-005")
        assert self._contains_harmful(post["text"])

    def test_post_006_is_harmful(self):
        post = next(p for p in POSTS if p["id"] == "POST-006")
        assert self._contains_harmful(post["text"])

    def test_post_007_is_borderline(self):
        post = next(p for p in POSTS if p["id"] == "POST-007")
        assert self._contains_borderline(post["text"])

    def test_post_008_is_borderline(self):
        post = next(p for p in POSTS if p["id"] == "POST-008")
        assert self._contains_borderline(post["text"])

    def test_post_009_is_borderline(self):
        post = next(p for p in POSTS if p["id"] == "POST-009")
        assert self._contains_borderline(post["text"])

    def test_post_001_is_safe(self):
        post = next(p for p in POSTS if p["id"] == "POST-001")
        assert not self._contains_harmful(post["text"])
        assert not self._contains_borderline(post["text"])

    def test_case_insensitive_matching(self):
        assert self._contains_harmful("We should DESTROY them")
        assert self._contains_harmful("This is a SCAM")


class TestCaches:
    """Test cache behavior."""

    def setup_method(self):
        screening_cache.clear()
        review_cache.clear()
        notice_cache.clear()

    def test_screening_cache_stores_result(self):
        screening_cache["test"] = {"classification": "safe", "confidence": "HIGH"}
        assert "test" in screening_cache
        assert screening_cache["test"]["classification"] == "safe"

    def test_review_cache_stores_result(self):
        review_cache["test"] = {"verdict": "harmful", "reason": "test"}
        assert "test" in review_cache

    def test_notice_cache_stores_result(self):
        notice_cache["test"] = {"post_id": "test", "message": "test"}
        assert "test" in notice_cache


class TestDeepReviewVerdicts:
    """Test the deep review verdict mappings."""

    def test_post_007_review_is_safe(self):
        verdict = DEEP_REVIEW_VERDICTS["POST-007"]
        assert verdict["verdict"] == "safe"

    def test_post_008_review_is_harmful(self):
        verdict = DEEP_REVIEW_VERDICTS["POST-008"]
        assert verdict["verdict"] == "harmful"

    def test_post_009_review_is_safe(self):
        verdict = DEEP_REVIEW_VERDICTS["POST-009"]
        assert verdict["verdict"] == "safe"


class TestNoticeTemplates:
    """Test notice generation templates."""

    def test_harmful_notice_exists(self):
        assert "harmful" in NOTICE_TEMPLATES
        template = NOTICE_TEMPLATES["harmful"]
        assert isinstance(template, str)
        assert len(template) > 20


class TestPipelineLogic:
    """Test pipeline routing logic without AWS calls."""

    def test_classification_hierarchy(self):
        """Verify expected classification for each post."""
        for post in POSTS:
            text_lower = post["text"].lower()
            has_harmful = any(kw in text_lower for kw in HARMFUL_KEYWORDS)
            has_borderline = any(kw in text_lower for kw in BORDERLINE_KEYWORDS)
            
            if post["id"] in ("POST-004", "POST-005", "POST-006"):
                assert has_harmful, f"{post['id']} should have harmful keywords"
            elif post["id"] in ("POST-007", "POST-008", "POST-009"):
                assert has_borderline, f"{post['id']} should have borderline keywords"
            else:
                assert not has_harmful
                assert not has_borderline

    def test_review_verdicts_coverage(self):
        """All borderline posts should have review verdicts."""
        borderline_ids = [
            p["id"] for p in POSTS
            if any(kw in p["text"].lower() for kw in BORDERLINE_KEYWORDS)
        ]
        for post_id in borderline_ids:
            assert post_id in DEEP_REVIEW_VERDICTS


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_string_not_harmful(self):
        assert not any(kw in "" for kw in HARMFUL_KEYWORDS)
        assert not any(kw in "" for kw in BORDERLINE_KEYWORDS)

    def test_keyword_length(self):
        """All keywords should be longer than 1 character."""
        for kw in HARMFUL_KEYWORDS + BORDERLINE_KEYWORDS:
            assert len(kw) > 1
