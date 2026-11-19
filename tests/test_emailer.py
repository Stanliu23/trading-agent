from datetime import datetime

import pytest

from tradeagent import db, email_samples, emailer
from tradeagent.config import load_config
from tradeagent.emailer import Email, Footer, Line, Section


@pytest.fixture
def cfg(project):
    (project / "config.local.yaml").write_text("email:\n  to: you@example.com\n  from: agent@example.com\n")
    return load_config(project)


class FakeSMTP:
    sent = []

    def __init__(self, host, port, context=None, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, password):
        self.user, self.password = user, password

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture(autouse=True)
def clear_fake():
    FakeSMTP.sent = []


def test_all_samples_render_and_pass_evidence_check():
    for name, build in email_samples.ALL.items():
        em = build(shadow=True)
        assert emailer.evidence_check(em) == [], name
        text, html = emailer.render_text(em, True), emailer.render_html(em, True)
        assert "SHADOW RUN" in text and "SHADOW RUN" in html
        assert "This agent cannot place trades." in text and "cannot place trades" in html
        assert em.subject.startswith("[SHADOW] ")
        assert "$" in em.subject                      # dollar amounts in subjects (approved)


def test_card_shows_required_fields():
    text = emailer.render_text(email_samples.digest(False), False)
    for must in ("[TIER 2", "★★★★☆", "Size", "Max loss", "Funding", "Sell $75 of BIL first", "Stars", "Why buy", "Why now",
                 "Tier 1 (low risk): none qualified today", "SELLS FOR TOMORROW", "BUY  DDDD", "Tier 3: half-size"):
        assert must in text


def test_evidence_check_catches_untagged_numbers():
    em = Email("digest", "Daily · x", Line("Buy 3 shares", None), [Section("A", [Line("up 4.1%", None)])],
               Footer("now", None, "x"))
    assert emailer.evidence_check(em) == ["Buy 3 shares", "up 4.1%"]


def test_send_dedupes_and_caps_urgent(cfg, tmp_path, memory_keyring):
    from tradeagent import secrets
    secrets.set_secret("gmail_app_password", "app-pass")
    conn = db.connect(db.init_db(tmp_path / "a.db"))
    now = datetime(2026, 11, 19, 10, 0).astimezone()
    first = email_samples.urgent(True)
    assert emailer.send(first, cfg, conn=conn, smtp_factory=FakeSMTP, now=now) == "sent"
    assert emailer.send(first, cfg, conn=conn, smtp_factory=FakeSMTP, now=now).startswith("suppressed: duplicate")
    for i in range(cfg.email.urgent_daily_cap - 1):
        em = Email("urgent", f"URGENT · test {i}", Line("x", None), [], first.footer)
        assert emailer.send(em, cfg, conn=conn, smtp_factory=FakeSMTP, now=now) == "sent"
    over = Email("urgent", "URGENT · one too many", Line("x", None), [], first.footer)
    assert "cap" in emailer.send(over, cfg, conn=conn, smtp_factory=FakeSMTP, now=now)
    assert len(FakeSMTP.sent) == cfg.email.urgent_daily_cap
    msg = FakeSMTP.sent[0]
    assert msg["To"] == "you@example.com" and "agent@example.com" in msg["From"]
    assert {p.get_content_type() for p in msg.iter_parts()} == {"text/plain", "text/html"}


def test_send_refuses_without_password_or_tags(cfg, tmp_path):
    conn = db.connect(db.init_db(tmp_path / "a.db"))
    with pytest.raises(RuntimeError, match="gmail_app_password"):
        emailer.send(email_samples.digest(True), cfg, conn=conn, smtp_factory=FakeSMTP)
    bad = Email("digest", "Daily", Line("up 5%", None), [], Footer("now", None, "x"))
    with pytest.raises(ValueError, match="source tag"):
        emailer.send(bad, cfg, conn=conn, smtp_factory=FakeSMTP)


def test_money_formatting():
    assert emailer.usd(1234.5) == "$1,234" or emailer.usd(1234.5) == "$1,235"
    assert emailer.usd(-6.6, signed=True) == "−$6.60" and emailer.usd(1.2, signed=True) == "+$1.20"
    assert emailer.pct(0.004) == "+0.4%" and emailer.pct(-0.06) == "−6.0%"


def test_samples_respect_position_cap():
    """Sample cards must follow the real rules: no position above 25% of the account."""
    import re
    text = emailer.render_text(email_samples.digest(False), False)
    for m in re.finditer(r"= (\d+\.\d)% of account", text):
        assert float(m.group(1)) <= 25.0


def test_every_action_is_boxed():
    """Rule: anything you would do in the Schwab app is in a box (Card or ActionBox)."""
    from tradeagent.emailer import ActionBox, Card
    for name, build in email_samples.ALL.items():
        em = build(False)
        for sec in em.sections:
            if sec.title.lower().startswith(("action", "recommendations", "long-term", "sells", "buys")):
                assert any(isinstance(b, (Card, ActionBox)) for b in sec.blocks) or all(
                    "none qualified" in getattr(b, "text", "") for b in sec.blocks), (name, sec.title)
    assert "<div style=\"border:1px solid" in emailer.render_html(email_samples.urgent(False), False)


def test_digest_lists_several_sells_and_buys_sells_first():
    from tradeagent.emailer import ActionBox, Card
    em = email_samples.digest(False)
    titles = [sec.title.lower() for sec in em.sections]
    assert titles.index(next(t for t in titles if t.startswith("sells"))) < titles.index("buys for tomorrow")
    sells = next(sec for sec in em.sections if sec.title.lower().startswith("sells"))
    buys = next(sec for sec in em.sections if sec.title.lower() == "buys for tomorrow")
    assert sum(isinstance(b, ActionBox) for b in sells.blocks) == 2
    assert sum(isinstance(b, Card) for b in buys.blocks) == 2
    assert "4 actions" in em.subject
