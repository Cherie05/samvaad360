"""Small, escaped presentation components for the public lending workspace."""
from __future__ import annotations

from datetime import datetime
from html import escape


CSS = """
<style>
:root {--ink:#18332a;--muted:#63756b;--green:#13795b;--line:#dce5df;--paper:#fff;--warm:#f5f7f5}
.sr-only {position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.stApp {background:var(--warm);color:var(--ink)}
.block-container {max-width:1460px;padding:3.7rem 2.6rem 2.5rem}
h1,h2,h3,h4 {color:var(--ink);letter-spacing:-.035em;line-height:1.16!important;font-family:Inter,ui-sans-serif,system-ui,sans-serif}
h1 {font-size:2.7rem!important;font-weight:750!important}
h2 {font-size:1.75rem!important} h3 {font-size:1.16rem!important;letter-spacing:-.02em}
p,li {line-height:1.58}
[data-testid="stSidebar"] {background:#eef3ef;border-right:1px solid var(--line)}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {padding-top:1.7rem}
[data-testid="stHeader"] {background:rgba(245,247,245,.93)}
[data-testid="stMetric"] {background:white;border:1px solid var(--line);border-radius:15px;padding:1rem}
[data-testid="stMetricLabel"] p {color:var(--muted);font-size:.82rem}
[data-testid="stMetricValue"] {font-size:1.9rem!important;font-weight:700}
[data-testid="stVerticalBlockBorderWrapper"]>div {border-radius:16px!important;border-color:var(--line)!important;background:#fff}
button[kind="primary"] {border-radius:9px;background:var(--green);border-color:var(--green);font-weight:650}
button[kind="secondary"] {border-radius:9px;border-color:#ccd9d1;background:#fff}
[data-baseweb="tab-list"] {gap:1.2rem;background:transparent;border-bottom:1px solid var(--line);padding-bottom:0}
[data-baseweb="tab"] {height:3.7rem;padding:.8rem .15rem;font-weight:600;font-size:.9rem;white-space:nowrap}
[data-baseweb="tab-highlight"] {background:var(--green)}
[data-testid="stExpander"] {border-radius:12px!important;border-color:var(--line)!important;background:white}
[data-testid="stForm"] {border-color:var(--line)!important;border-radius:12px;background:#fafcfb}
[data-testid="stCaptionContainer"] p {color:var(--muted);line-height:1.45}
.brand {display:flex;align-items:center;gap:10px;margin-bottom:2rem}
.brand-icon {display:grid;place-items:center;width:39px;height:39px;background:#12392e;color:white;border-radius:11px;font-size:23px;font-weight:700}
.brand-name {font-size:1.4rem;font-weight:760;letter-spacing:-.07em;color:#143c2d;line-height:1.1}
.brand-name span {font-weight:430;color:#6d8276;font-size:1.1rem}
.brand-tag {font-size:.62rem;text-transform:uppercase;letter-spacing:.15em;color:#75877b;margin-top:5px}
.sidebar-label {color:#65796b;font-weight:650;font-size:.67rem;letter-spacing:.13em;text-transform:uppercase;margin:1.15rem 0 .5rem}
.sidebar-note {color:#65766c;font-size:.76rem;line-height:1.65;padding-top:.35rem}
.eyebrow {font-weight:700;color:#718276;font-size:.66rem;letter-spacing:.15em;text-transform:uppercase;margin-bottom:.3rem}
.topline {display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:.8rem;font-size:.75rem;color:#677b6e}
.live-pill {display:inline-flex;gap:7px;align-items:center;background:#e4f3e8;border:1px solid #c6e5cf;color:#236943;padding:5px 10px;border-radius:100px;font-size:.7rem;font-weight:650}
.live-dot {width:6px;height:6px;background:#3b9565;border-radius:100px}
.hero {position:relative;background:#143d2e;color:#e3f0e6;border-radius:19px;padding:2rem 2.2rem;margin:.75rem 0 1.4rem;overflow:hidden;min-height:190px}
.hero:after {content:'';position:absolute;width:250px;height:250px;border:1px solid #37644d;border-radius:50%;right:1rem;top:-74px;box-shadow:0 0 0 38px rgba(87,143,107,.08),0 0 0 78px rgba(87,143,107,.05)}
.hero .eyebrow {color:#9cc5ab;position:relative;z-index:1}
.hero h2 {color:white;font-size:2.2rem!important;max-width:670px;position:relative;z-index:1;margin:.55rem 0 .65rem}
.hero p {color:#c0d6c7;font-size:.88rem;max-width:610px;position:relative;z-index:1;margin:0}
.hero-tag {display:inline-flex;background:#2c5640;border:1px solid #45765b;color:#d8e9dc;padding:5px 10px;border-radius:100px;font-size:.7rem;margin-top:1rem;position:relative;z-index:1}
.metric-grid {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin:.7rem 0 1.6rem}
.metric-card {background:white;border:1px solid var(--line);border-radius:14px;padding:1.08rem 1.15rem;min-width:0}
.metric-card .label {font-size:.74rem;color:#75877d;font-weight:550}
.metric-card .value {font-size:1.9rem;line-height:1.25;color:#193c2b;font-weight:740;letter-spacing:-.06em;margin:.4rem 0 .25rem}
.metric-card .detail {font-size:.69rem;color:#718378;line-height:1.4}
.section-head {display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin:1.1rem 0 .7rem}
.section-head h3,.section-head h3 span {margin:0;font-size:1.12rem!important;font-weight:700;color:#284936}
.section-head>span {color:#7c8c81;font-size:.72rem}
.chip {display:inline-block;padding:4px 9px;border-radius:6px;font-size:.66rem;font-weight:650;margin:3px 5px 3px 0;border:1px solid transparent;letter-spacing:.01em}
.chip.green {background:#e8f4eb;color:#2a7044;border-color:#d4e7d8}
.chip.amber {background:#fff1d9;color:#96611c;border-color:#eedebe}
.chip.red {background:#fbe9e6;color:#a54e46;border-color:#f0d2cc}
.chip.blue {background:#eaf0f6;color:#41688c;border-color:#d9e4ed}
.chip.gray {background:#f0f3f1;color:#667a6d;border-color:#e2e8e4}
.identity {display:flex;align-items:center;gap:15px;margin:.7rem 0 1rem}
.avatar {display:grid;place-items:center;width:62px;height:62px;border-radius:17px;background:#dfebe1;color:#2c6446;font-size:1.4rem;font-weight:650;flex-shrink:0}
.identity h2 {margin:0 0 4px;font-size:1.85rem!important}
.identity .meta {font-size:.76rem;color:#77867c}
.action-card {border-left:4px solid #3b9270;padding:.15rem 0 .15rem 1rem;margin:.55rem 0 1.2rem}
.action-card h3 {margin:.35rem 0 .6rem;font-size:1.32rem!important;line-height:1.3!important}
.action-card p {font-size:.86rem;color:#627267;line-height:1.65;margin:.25rem 0}
.field-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:.7rem 0}
.field {border:1px solid #e3ebe6;background:#f6f9f7;padding:.7rem .8rem;border-radius:9px;min-width:0}
.field .label {font-size:.67rem;color:#788a7e;line-height:1.4}.field .value {font-size:1.04rem;font-weight:650;color:#234735;margin-top:4px}
.reason {font-size:.8rem;color:#5e7364;line-height:1.65;background:#f1f7f3;border:1px solid #dce8df;border-radius:10px;padding:12px 14px;margin:10px 0}
.evidence-card {border:1px solid #e0e8e3;border-radius:12px;padding:1rem 1.1rem;margin:.55rem 0;background:#fff}
.evidence-top {display:flex;justify-content:space-between;align-items:center;font-size:.67rem;color:#7b8b80;gap:8px}
.evidence-card blockquote {border-left:3px solid #95bda3;padding:.1rem 0 .1rem .8rem;margin:.7rem 0;color:#344f3e;font-size:.84rem;line-height:1.75}
.evidence-card .source {font-size:.66rem;font-weight:550;color:#87958c;margin-top:.65rem}
.timeline {position:relative;margin:.5rem 0;padding-left:1.65rem;border-left:2px solid #dae6dd}
.journey-item {position:relative;margin:0 0 1.25rem}
.journey-item:before {position:absolute;content:'';width:10px;height:10px;border-radius:50%;background:#729b7b;left:-1.98rem;top:5px;border:3px solid #f5f7f5}
.journey-item .stamp {color:#829386;font-size:.65rem;letter-spacing:.025em}
.journey-item .title {font-weight:650;font-size:.86rem;margin:4px 0;color:#31513b}
.journey-item .excerpt {font-size:.78rem;line-height:1.7;color:#687b6c;white-space:pre-wrap}
.priority-name {font-size:.9rem;font-weight:680;color:#284936;margin:.1rem 0 .3rem}.priority-meta {font-size:.71rem;color:#819084}
.scenario-copy {min-height:87px;margin:.25rem 0 .75rem}.scenario-copy h3 {font-size:1.05rem!important;margin:.35rem 0 .45rem}.scenario-copy p {font-size:.76rem;color:#76867b;line-height:1.6;margin:0}
.check-row {display:flex;gap:9px;margin:.7rem 0;font-size:.77rem;line-height:1.55;color:#617468}
.check-icon {font-weight:750;color:#258057;flex-shrink:0}.check-icon.blocked {color:#b56645}
.check-row strong {font-size:.79rem;color:#36543e}.check-row .small {color:#7a8b7e;font-size:.72rem}
.compare-card {padding:1rem;border:1px solid #dae5dc;border-radius:12px;background:#f7faf8;height:100%}.compare-card .eyebrow {font-size:.61rem}.compare-card h4 {font-size:1rem;margin:.35rem 0;color:#30533b}.compare-card p {font-size:.77rem;color:#77867b}
.empty-state {text-align:center;padding:2.2rem 1.1rem;border:1px dashed #cbdccf;border-radius:14px;background:#f8fbf9;margin:.7rem 0 1rem}.empty-state .symbol {font-size:1.9rem;color:#8ba995;margin-bottom:.5rem}.empty-state h3 {font-size:1.18rem;margin:.5rem 0}.empty-state p {font-size:.8rem;color:#7a8b7e;max-width:430px;margin:.5rem auto}
.transcript {padding:.6rem 0}.turn {max-width:95%;padding:13px 15px;border-radius:13px;margin:.5rem 0;font-size:.84rem;line-height:1.65}.turn.assistant {background:#eaf3ed;border:1px solid #d6e6da;color:#2e5140}.turn.customer {background:#f1f3f6;border:1px solid #e3e7ec;color:#4a5d6f;margin-left:1.5rem}.turn .speaker {display:block;font-size:.62rem;font-weight:750;text-transform:uppercase;letter-spacing:.1em;margin-bottom:5px;opacity:.65}
.turn,.journey-item .excerpt,.evidence-card blockquote,.reason {overflow-wrap:anywhere;word-break:break-word}
.call-status {border-radius:12px;background:#edf5ef;border:1px solid #d6e7dc;padding:.75rem 1rem;color:#326342;font-size:.77rem;margin:.65rem 0}.footer {display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;border-top:1px solid #dce5df;margin-top:2.3rem;padding-top:1rem;font-size:.67rem;color:#8b988f}
@media(max-width:900px) {.block-container {padding:3.7rem 1.3rem 2rem}.hero h2 {font-size:1.8rem!important}.hero:after {opacity:.5}.metric-card .value {font-size:1.65rem}}
@media(max-width:640px) {.block-container {padding:3.7rem .95rem 2rem}h1 {font-size:2rem!important}.topline {font-size:.65rem}.metric-grid {grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.metric-card {padding:.8rem .9rem}.metric-card .value {font-size:1.55rem}.hero {padding:1.5rem 1.2rem;min-height:165px}.hero h2 {font-size:1.6rem!important}.hero p {font-size:.79rem}.hero:after {display:none}.hero-tag {font-size:.61rem}.identity h2 {font-size:1.55rem!important}.field-grid {gap:7px}.section-head {align-items:flex-start}.section-head>span {max-width:42%;text-align:right}.turn {max-width:100%}[data-baseweb="tab-list"] {gap:1rem;overflow-x:auto}[data-baseweb="tab"] {font-size:.8rem}}
</style>
"""


def safe(value):
    return escape(str(value), quote=True)


def money(value):
    value = float(value or 0)
    if abs(value) >= 10000000:
        return f"Rs {value / 10000000:,.2f} Cr"
    if abs(value) >= 100000:
        return f"Rs {value / 100000:,.2f} L"
    return f"Rs {value:,.0f}"


def date_label(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%d %b %Y")
    except (ValueError, TypeError):
        return str(value)


def chip(label, tone="gray"):
    tone = tone if tone in {"gray", "green", "amber", "red", "blue"} else "gray"
    return f'<span class="chip {tone}">{safe(label)}</span>'


def section(title, detail=""):
    return f'<div class="section-head"><h3>{safe(title)}</h3><span>{safe(detail)}</span></div>'


def metric_grid(items):
    cards = ''.join(f'<div class="metric-card"><div class="label">{safe(label)}</div>'
                    f'<div class="value">{safe(value)}</div><div class="detail">{safe(detail)}</div></div>'
                    for label, value, detail in items)
    return '<div class="metric-grid">' + cards + '</div>'


def fields(items):
    if not items:
        return ''
    return '<div class="field-grid">' + ''.join(
        f'<div class="field"><div class="label">{safe(item["label"])}</div>'
        f'<div class="value">{safe(item["value"])}</div></div>' for item in items) + '</div>'


def evidence_card(item):
    sentiment = float(item.get("sentiment", 0))
    tone, label = ("red", "Needs care") if sentiment < -.3 else ("green", "Positive") if sentiment > .2 else ("gray", "Neutral")
    return (f'<div class="evidence-card"><div class="evidence-top"><span>{safe(item.get("channel", "Interaction").title())}'
            f' &middot; {safe(date_label(item.get("ts", "")))}</span>{chip(label, tone)}</div>'
            f'<blockquote>{safe(item.get("text", item.get("evidence_text", "")))}</blockquote>'
            f'<div class="source">{safe(item.get("id", item.get("interaction_id", "")))}'
            f' &middot; {safe(item.get("intent", "Recorded interaction"))}</div></div>')


def empty_state(title, description, symbol="○"):
    return (f'<div class="empty-state"><div class="symbol">{safe(symbol)}</div>'
            f'<h3>{safe(title)}</h3><p>{safe(description)}</p></div>')
