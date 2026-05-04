#!/usr/bin/env python3
"""Query token usage for the last N hours."""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

HISTORY_FILE = Path.home() / ".qode" / "token_usage" / "token_history.json"


def load_history() -> list[dict]:
    """Load call history from disk."""
    if not HISTORY_FILE.exists():
        return []
    with open(HISTORY_FILE, "r") as f:
        return json.load(f)


def query_last_hours(hours: int = 96) -> dict:
    """Query token usage for the last N hours."""
    history = load_history()
    if not history:
        return {"hours": hours, "calls": [], "summary": None}

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    filtered = [
        call for call in history
        if datetime.fromisoformat(call["timestamp"]) >= cutoff
    ]

    if not filtered:
        return {"hours": hours, "calls": [], "summary": None}

    # Calculate summary
    total_prompt = sum(c["prompt_tokens"] for c in filtered)
    total_completion = sum(c["completion_tokens"] for c in filtered)
    total = sum(c["total_tokens"] for c in filtered)

    # Group by model
    by_model = {}
    for call in filtered:
        model = call["model"]
        by_model[model] = by_model.get(model, 0) + call["total_tokens"]

    return {
        "hours": hours,
        "calls": filtered,
        "summary": {
            "call_count": len(filtered),
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total,
            "by_model": by_model,
        }
    }


def print_usage(result: dict):
    """Pretty-print usage results."""
    print(f"\n📊 Token Usage — Last {result['hours']} Hours")
    print("=" * 70)

    if not result["calls"]:
        print("No calls recorded in this period.")
        return

    summary = result["summary"]
    print(f"\n📈 Summary:")
    print(f"  Calls:           {summary['call_count']}")
    print(f"  Prompt tokens:   {summary['total_prompt_tokens']:,}")
    print(f"  Completion:      {summary['total_completion_tokens']:,}")
    print(f"  Total:           {summary['total_tokens']:,}")

    print(f"\n🔧 By Model:")
    for model, tokens in sorted(summary["by_model"].items()):
        print(f"  {model:40} {tokens:,} tokens")

    print(f"\n📋 Call Details:")
    print(f"  {'Time':<26} {'Prompt':>8} {'Compl':>8} {'Total':>8} Model")
    print("-" * 70)
    for call in result["calls"]:
        ts = datetime.fromisoformat(call["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"  {ts} {call['prompt_tokens']:>8} {call['completion_tokens']:>8} "
            f"{call['total_tokens']:>8} {call['model']}"
        )


if __name__ == "__main__":
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 96
    result = query_last_hours(hours)
    print_usage(result)
