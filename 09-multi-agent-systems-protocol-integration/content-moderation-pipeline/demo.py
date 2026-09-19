#!/usr/bin/env python3
"""
Demonstration script for content-moderation-pipeline.

This script shows what the pipeline would do for each test post
without requiring actual AWS calls.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from main import (
    POSTS,
    HARMFUL_KEYWORDS,
    BORDERLINE_KEYWORDS,
    DEEP_REVIEW_VERDICTS,
    NOTICE_TEMPLATES,
    screening_cache,
    review_cache,
    notice_cache,
)


def classify_post(text: str) -> str:
    """Classify a post based on keyword detection."""
    text_lower = text.lower()
    
    if any(kw in text_lower for kw in HARMFUL_KEYWORDS):
        return "HARMFUL"
    elif any(kw in text_lower for kw in BORDERLINE_KEYWORDS):
        return "BORDERLINE"
    else:
        return "SAFE"


def simulate_pipeline(post: dict) -> dict:
    """
    Simulate the pipeline logic without making AWS calls.
    
    This shows what the real pipeline would do:
    1. Screen the post
    2. If borderline, do deep review
    3. If harmful, generate notice
    """
    post_id = post["id"]
    text = post["text"]
    
    # Step 1: Screening
    classification = classify_post(text)
    
    # Step 2: Deep review (only if borderline)
    final_verdict = classification
    review_result = None
    
    if classification == "BORDERLINE":
        # In real pipeline, this would call Claude Sonnet
        review_result = DEEP_REVIEW_VERDICTS.get(post_id, {})
        if review_result:
            final_verdict = review_result.get("verdict", "safe").upper()
    
    # Step 3: Notice (only if final verdict is harmful)
    notice_result = None
    if final_verdict == "HARMFUL":
        notice_result = {
            "post_id": post_id,
            "message": NOTICE_TEMPLATES["harmful"]
        }
    
    return {
        "post_id": post_id,
        "text_preview": text[:50] + "..." if len(text) > 50 else text,
        "classification": classification,
        "final_verdict": final_verdict,
        "review": review_result,
        "notice": notice_result,
    }


def print_separator():
    print("\n" + "=" * 70)


def demo_pipeline():
    """Run the pipeline simulation for all posts."""
    print("\n" + "=" * 70)
    print("CONTENT MODERATION PIPELINE - DEMONSTRATION")
    print("=" * 70)
    print(f"\nModel Configuration:")
    print(f"  - Screening: Nova Lite (temperature 0.0)")
    print(f"  - Deep Review: Claude Sonnet (temperature 0.1)")
    print(f"  - Notice: Nova Pro (temperature 0.3)")
    print(f"\nKeyword Configuration:")
    print(f"  - Harmful keywords: {HARMFUL_KEYWORDS}")
    print(f"  - Borderline keywords: {BORDERLINE_KEYWORDS}")
    print(f"\n")
    
    results = []
    for post in POSTS:
        result = simulate_pipeline(post)
        results.append(result)
        
        print_separator()
        print(f"POST: {result['post_id']}")
        print(f"TEXT: {result['text_preview']}")
        print(f"\nSTEP 1 - SCREENING (Nova Lite):")
        print(f"  Classification: {result['classification']}")
        
        if result['review']:
            print(f"\nSTEP 2 - DEEP REVIEW (Claude Sonnet):")
            print(f"  Verdict: {result['review'].get('verdict', 'N/A').upper()}")
            print(f"  Reason: {result['review'].get('reason', 'N/A')}")
        
        if result['notice']:
            print(f"\nSTEP 3 - NOTICE (Nova Pro):")
            print(f"  Message: {result['notice']['message']}")
        
        print(f"\nFINAL RESULT:")
        print(f"  Final Verdict: {result['final_verdict']}")
    
    # Summary
    print_separator()
    print("\nSUMMARY")
    print("=" * 70)
    
    safe_count = sum(1 for r in results if r['final_verdict'] == 'SAFE')
    harmful_count = sum(1 for r in results if r['final_verdict'] == 'HARMFUL')
    borderline_count = sum(1 for r in results if r['classification'] == 'BORDERLINE')
    
    print(f"\nTotal Posts: {len(POSTS)}")
    print(f"  - Safe (approved): {safe_count}")
    print(f"  - Harmful (removed): {harmful_count}")
    print(f"  - Borderline (required review): {borderline_count}")
    
    print(f"\nPipeline Flow:")
    print(f"  - Posts screened: {len(POSTS)}")
    print(f"  - Posts reviewed: {borderline_count}")
    print(f"  - Notices generated: {harmful_count}")
    
    return results


if __name__ == "__main__":
    demo_pipeline()
