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
    for must in ("[TIER 2", "★★★★☆", "Size", "Max loss", "Funding", "Sell $75 of BIL first", "Stars", "Tier 1: none qualified today"):
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
