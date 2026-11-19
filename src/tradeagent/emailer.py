"""Emails: render (HTML + plain text) and send through the agent's Gmail. Layouts follow docs/EMAILS.md.

Every email is built from the same pieces: a lead line, sections of lines/tables/cards, and the footer.
A line may carry a source tag; ``evidence_check`` rejects any line with a number but no tag.
"""

from __future__ import annotations

import hashlib
import html
import re
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Literal, Optional, Union

from tradeagent import db, secrets
from tradeagent.config import Config

Kind = Literal["urgent", "premarket", "digest", "weekly", "reminder"]
GREEN, RED, GREY, INK = "#137333", "#c5221f", "#5f6368", "#202124"
_NUMBER = re.compile(r"\d")


# --- building blocks ------------------------------------------------------------

@dataclass(frozen=True)
class Line:
    text: str
    source: Optional[str] = None       # e.g. "schwab 10:45", "setup S3"
    tone: Literal["plain", "up", "down", "muted", "strong", "heading"] = "plain"   # heading: a label, not data


@dataclass(frozen=True)
class Table:
    header: list[str]
    rows: list[list[str]]
    source: Optional[str] = None


@dataclass(frozen=True)
class Card:
    tier: int
    stars: int
    action: str                         # BUY / SELL / TRIM ...
    symbol: str
    bucket: str                         # "short-term" / "long-term"
    size: str                           # "$75 = 25.0% of account"
    entry: str                          # "Entry ≤ $84.50"
    stop: Optional[str]                 # "$79.40 (−6.0%)"; None for long-term
    target: Optional[str]
    thesis_rule: Optional[str]          # long-term only
    max_loss: str
    funding: Optional[str]
    odds: str
    odds_source: str
    why_buy: str                        # the setup's logic: why this kind of trade should work
    why_buy_source: str
    why: str                            # why now: today's trigger
    why_source: str
    stars_detail: str                   # "Edge 4 · Confidence 5 · Fit 3"


@dataclass(frozen=True)
class ActionBox:
    """A boxed action that is not a buy recommendation (e.g. sell at a stop). Rule: everything you would
    actually do in the Schwab app is in a box; everything else is information."""
    title: str
    lines: list[Line]


Block = Union[Line, Table, Card, ActionBox]


@dataclass(frozen=True)
class Section:
    title: str
    blocks: list[Block] = field(default_factory=list)


@dataclass(frozen=True)
class Footer:
    data_as_of: str                     # "16:30 ET, Nov 18"
    login_days_left: Optional[int]      # None when no Schwab login is in use
    account_source: str                 # "Schwab" / "hypothetical account"


@dataclass(frozen=True)
class Email:
    kind: Kind
    subject: str
    lead: Line                          # the one line that tells you what to do
    sections: list[Section]
    footer: Footer


# --- formatting helpers -------------------------------------------------------------

def usd(x: float, signed: bool = False) -> str:
    s = f"${abs(x):,.2f}" if abs(x) < 1000 else f"${abs(x):,.0f}"
    if signed:
        return ("+" if x >= 0 else "−") + s
    return ("−" if x < 0 else "") + s


def pct(x: float, signed: bool = True, digits: int = 1) -> str:
    s = f"{abs(x) * 100:.{digits}f}%"
    return (("+" if x >= 0 else "−") + s) if signed else s


def stars_text(n: int) -> str:
    return "★" * n + "☆" * (5 - n)


def subject_line(kind: Kind, parts: list[str], shadow: bool) -> str:
    label = {"urgent": "URGENT", "premarket": "Premarket", "digest": "Daily", "weekly": "Weekly",
             "reminder": "Reminder"}[kind]
    return ("[SHADOW] " if shadow else "") + " · ".join([label, *parts])


def evidence_check(email: Email) -> list[str]:
    """Lines that contain a number but carry no source tag (cards and tables carry their own)."""
    bad = []
    lines = [b for s in email.sections for b in s.blocks if isinstance(b, Line)]
    lines += [ln for s in email.sections for b in s.blocks if isinstance(b, ActionBox) for ln in b.lines]
    for line in [email.lead] + lines:
        if _NUMBER.search(line.text) and not line.source and line.tone not in ("muted", "heading"):
            bad.append(line.text)
    return bad


# --- plain text -----------------------------------------------------------------

def _tag(source: Optional[str]) -> str:
    return f"   [{source}]" if source else ""


def _card_text(c: Card) -> list[str]:
    out = [f"[TIER {c.tier} · {stars_text(c.stars)}]  {c.action}  {c.symbol}  · {c.bucket} bucket",
           f"Size      {c.size}   {c.entry}"]
    if c.stop:
        out.append(f"Stop      {c.stop}" + (f"   Target {c.target}" if c.target else ""))
    if c.thesis_rule:
        out.append(f"Sell if   {c.thesis_rule}")
    out.append(f"Max loss  {c.max_loss}")
    if c.funding:
        out.append(f"Funding   {c.funding}")
    out += [f"Why buy   {c.why_buy}{_tag(c.why_buy_source)}", f"Why now   {c.why}{_tag(c.why_source)}",
            f"Odds      {c.odds}{_tag(c.odds_source)}", f"Stars     {c.stars_detail}"]
    return out


def _table_text(t: Table) -> list[str]:
    widths = [max(len(str(r[i])) for r in [t.header] + t.rows) for i in range(len(t.header))]
    fmt = lambda r: "  ".join(str(v).ljust(w) for v, w in zip(r, widths)).rstrip()
    return [fmt(t.header)] + [fmt(r) for r in t.rows] + ([f"[{t.source}]"] if t.source else [])


def render_text(email: Email, shadow: bool) -> str:
    lines = []
    if shadow:
        lines += ["SHADOW RUN: hypothetical money. Do not act on this email.", ""]
    lines += [email.lead.text + _tag(email.lead.source), ""]
    for i, sec in enumerate(email.sections, 1):
        lines.append(f"{i}  {sec.title.upper()}")
        for b in sec.blocks:
            if isinstance(b, Line):
                lines.append("   " + b.text + _tag(b.source))
            elif isinstance(b, Table):
                lines += ["   " + x for x in _table_text(b)]
            elif isinstance(b, ActionBox):
                lines += [f"   [{b.title}]"] + ["   " + ln.text + _tag(ln.source) for ln in b.lines]
            else:
                lines += ["   " + x for x in _card_text(b)]
        lines.append("")
    lines.append(footer_text(email.footer))
    return "\n".join(lines) + "\n"


def footer_text(f: Footer) -> str:
    login = (f"Schwab login expires in {f.login_days_left} days" if f.login_days_left is not None
             else "no Schwab login in use")
    return f"Data as of {f.data_as_of} ({f.account_source}) · {login} · This agent cannot place trades at Schwab."


# --- HTML -------------------------------------------------------------------------

def _e(s: str) -> str:
    return html.escape(s, quote=True)


def _src(source: Optional[str]) -> str:
    return f' <span style="color:{GREY};font-size:11px">[{_e(source)}]</span>' if source else ""


def _line_html(b: Line) -> str:
    color = {"up": GREEN, "down": RED, "muted": GREY}.get(b.tone, INK)
    weight = "600" if b.tone in ("strong", "heading") else "400"
    top = "10px" if b.tone == "heading" else "4px"
    return f'<p style="margin:{top} 0 4px;color:{color};font-weight:{weight}">{_e(b.text)}{_src(b.source)}</p>'


def _table_html(t: Table) -> str:
    th = "".join(f'<th style="text-align:left;padding:4px 8px;border-bottom:1px solid #dadce0;font-size:12px;color:{GREY}">{_e(h)}</th>' for h in t.header)
    body = ""
    for r in t.rows:
        tds = ""
        for v in r:
            v = str(v)
            color = GREEN if v.startswith("+") else RED if v.startswith(("−", "-")) and any(ch.isdigit() for ch in v) else INK
            tds += f'<td style="padding:4px 8px;border-bottom:1px solid #f1f3f4;color:{color}">{_e(v)}</td>'
        body += f"<tr>{tds}</tr>"
    src = f'<p style="margin:2px 0 0;color:{GREY};font-size:11px">[{_e(t.source)}]</p>' if t.source else ""
    return f'<table style="border-collapse:collapse;width:100%;font-size:13px"><tr>{th}</tr>{body}</table>{src}'


def _card_html(c: Card) -> str:
    row = lambda k, v, src=None: (f'<tr><td style="padding:2px 8px 2px 0;color:{GREY};white-space:nowrap;vertical-align:top">{_e(k)}</td>'
                                  f'<td style="padding:2px 0">{_e(v)}{_src(src)}</td></tr>')
    rows = row("Size", f"{c.size} · {c.entry}")
    if c.stop:
        rows += row("Stop", c.stop + (f" · Target {c.target}" if c.target else ""))
    if c.thesis_rule:
        rows += row("Sell if", c.thesis_rule)
    rows += row("Max loss", c.max_loss)
    if c.funding:
        rows += row("Funding", c.funding)
    rows += (row("Why buy", c.why_buy, c.why_buy_source) + row("Why now", c.why, c.why_source)
             + row("Odds", c.odds, c.odds_source) + row("Stars", c.stars_detail))
    return (f'<div style="border:1px solid #dadce0;border-radius:8px;padding:10px 12px;margin:8px 0">'
            f'<div style="font-weight:600;margin-bottom:6px">Tier {c.tier} · <span style="color:#f9ab00">{stars_text(c.stars)}</span>'
            f' · {_e(c.action)} {_e(c.symbol)} <span style="color:{GREY};font-weight:400">· {_e(c.bucket)} bucket</span></div>'
            f'<table style="border-collapse:collapse;font-size:13px">{rows}</table></div>')


def _box_html(b: ActionBox) -> str:
    inner = "".join(_line_html(ln) for ln in b.lines)
    return (f'<div style="border:1px solid #dadce0;border-radius:8px;padding:10px 12px;margin:8px 0">'
            f'<div style="font-weight:600;margin-bottom:4px">{_e(b.title)}</div>{inner}</div>')


def render_html(email: Email, shadow: bool) -> str:
    parts = ['<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;font-size:14px;color:#202124;'
             'max-width:620px;margin:0 auto;padding:8px">']
    if shadow:
        parts.append('<div style="background:#fef7e0;border:1px solid #f9ab00;border-radius:6px;padding:8px;margin-bottom:10px">'
                     '<b>SHADOW RUN:</b> hypothetical money. Do not act on this email.</div>')
    parts.append(f'<p style="font-size:16px;font-weight:600;margin:6px 0 12px">{_e(email.lead.text)}{_src(email.lead.source)}</p>')
    for i, sec in enumerate(email.sections, 1):
        parts.append(f'<h3 style="font-size:13px;letter-spacing:.04em;color:{GREY};margin:16px 0 4px">{i} · {_e(sec.title.upper())}</h3>')
        for b in sec.blocks:
            parts.append(_line_html(b) if isinstance(b, Line) else _table_html(b) if isinstance(b, Table)
                         else _box_html(b) if isinstance(b, ActionBox) else _card_html(b))
    parts.append(f'<p style="color:{GREY};font-size:11px;border-top:1px solid #dadce0;margin-top:18px;padding-top:8px">'
                 f'{_e(footer_text(email.footer))}</p></div>')
    return "".join(parts)


# --- sending -----------------------------------------------------------------------

SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465


def build_message(email: Email, config: Config, shadow: bool) -> EmailMessage:
    sender, to = config.local.email.from_, config.local.email.to
    if not sender or not to:
        raise ValueError("config.local.yaml needs email.from and email.to")
    msg = EmailMessage()
    msg["Subject"] = email.subject
    msg["From"] = f"Trading agent <{sender}>"
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    msg.set_content(render_text(email, shadow))
    msg.add_alternative(render_html(email, shadow), subtype="html")
    return msg


def body_hash(email: Email) -> str:
    return hashlib.sha256((email.subject + render_text(email, False)).encode()).hexdigest()


def should_send(conn, email: Email, config: Config, today: date) -> tuple[bool, str]:
    """Suppress exact duplicates, and urgent emails past the daily cap."""
    h = body_hash(email)
    if conn.execute("SELECT 1 FROM emails WHERE body_hash = ? AND status = 'sent'", (h,)).fetchone():
        return False, "duplicate"
    if email.kind == "urgent":
        n = conn.execute("SELECT COUNT(*) FROM emails WHERE kind = 'urgent' AND status = 'sent' AND substr(sent_at, 1, 10) = ?",
                         (today.isoformat(),)).fetchone()[0]
        if n >= config.email.urgent_daily_cap:
            return False, f"urgent cap of {config.email.urgent_daily_cap} per day reached"
    return True, ""


def send(email: Email, config: Config, *, conn=None, smtp_factory=smtplib.SMTP_SSL, now: datetime | None = None) -> str:
    """Send one email through Gmail (app password from the Keychain). Returns 'sent' or 'suppressed: …'."""
    now = now or datetime.now().astimezone()
    shadow = config.mode == "shadow"
    if evidence_check(email):
        raise ValueError(f"numbers without a source tag: {evidence_check(email)}")
    own = conn is None
    conn = conn or db.connect(db.init_db())   # init_db is idempotent: adds tables new versions need
    try:
        ok, why = should_send(conn, email, config, now.date())
        status = "sent"
        if ok:
            password = secrets.get_secret("gmail_app_password")
            if not password:
                raise RuntimeError("gmail_app_password is not in the Keychain (uv run tradeagent set-secret gmail_app_password)")
            msg = build_message(email, config, shadow)
            with smtp_factory(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=30) as smtp:
                smtp.login(config.local.email.from_, password)
                smtp.send_message(msg)
        else:
            status = "suppressed"
        conn.execute("INSERT INTO emails(sent_at, kind, subject, shadow, status, body_hash) VALUES (?,?,?,?,?,?)",
                     (now.isoformat(timespec="seconds"), email.kind, email.subject, int(shadow), status, body_hash(email)))
        conn.commit()
        return status if ok else f"suppressed: {why}"
    finally:
        if own:
            conn.close()


def check_login(config: Config, smtp_factory=smtplib.SMTP_SSL) -> str:
    """Log in to Gmail without sending anything."""
    password = secrets.get_secret("gmail_app_password")
    if not (config.local.email.from_ and password):
        return "missing email.from or gmail_app_password"
    with smtp_factory(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.login(config.local.email.from_, password)
    return "ok"
