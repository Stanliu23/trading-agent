import subprocess
from datetime import datetime

from tradeagent import ideas

TEXT = """# Ideas from GitHub, week of 2026-11-27
Some intro the parser ignores.
## 1. Volatility-scaled position sizing
- What: size each trade so every position risks the same share of the account's daily swings.
- Source: https://github.com/example/bot
- License: MIT
- Better than ours because: our sizes ignore how jumpy a stock is.
- Would change: risk.size_position.
- How it would be tested: 36-start account test, fixed bar.
- Verdict: can build
## 2. <script>alert(1)</script> Second idea
- What: """ + "x" * 400 + """
- Verdict: cannot build (needs paid intraday data)
## 3. Third
- Verdict: can build
## 4. Fourth is dropped
- Verdict: can build
"""


def fake(text, fetch_ok=True):
    calls = []
    def run(cmd, **kw):
        calls.append(cmd)
        if "fetch" in cmd:
            return subprocess.CompletedProcess(cmd, 0 if fetch_ok else 1, "", "")
        return subprocess.CompletedProcess(cmd, 0 if text else 128, text or "", "")
    return run, calls


def test_parses_at_most_three_and_cleans_text():
    week, items = ideas.parse(TEXT)
    assert str(week) == "2026-11-27" and len(items) == 3
    assert items[0]["License"] == "MIT" and items[0]["Would change"] == "risk.size_position."
    assert "<" not in items[1]["title"] and len(items[1]["What"]) <= ideas.MAX_FIELD


def test_weekly_section_lists_proposals_and_how_to_approve():
    run, calls = fake(TEXT)
    lines = ideas.weekly_lines(datetime(2026, 11, 28, 9), run=run)
    assert len(lines) == 4 and lines[0].text.startswith("1. Volatility-scaled position sizing.")
    assert "approve idea N from the week of 2026-11-27" in lines[-1].text
    assert all("checkout" not in c and "merge" not in c and "push" not in c for c in calls)   # read only


def test_old_or_missing_lists_say_so():
    run, _ = fake(TEXT)
    assert "No new ideas" in ideas.weekly_lines(datetime(2026, 12, 12, 9), run=run)[0].text
    run, _ = fake(None, fetch_ok=False)
    assert "No ideas from GitHub yet" in ideas.weekly_lines(datetime(2026, 11, 28, 9), run=run)[0].text
