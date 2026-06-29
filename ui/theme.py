from __future__ import annotations

from collections.abc import Iterable

import streamlit as st

from core.schemas import InspectionDecision
from ui.formatters import (
    decision_label,
    format_confidence,
    format_seconds,
    format_speedup,
    html_escape,
    normalize_status,
)


APP_BACKGROUND = "#050A18"
SIDEBAR_BACKGROUND = "#07101F"
PANEL_BACKGROUND = "#0C1426"
ELEVATED_PANEL = "#101B31"
CONSOLE_BACKGROUND = "#020817"
PRIMARY_BORDER = "#20304A"
SUBTLE_BORDER = "#17243A"
PRIMARY_TEAL = "#12D6A0"
BRIGHT_TEAL = "#20F0B6"
SECONDARY_CYAN = "#35CFF3"
SUCCESS_GREEN = "#22C983"
WARNING_AMBER = "#F5B942"
REWORK_ORANGE = "#FF8A3D"
REJECT_RED = "#FF4D5F"
FAILURE_RED = "#D83A52"
PRIMARY_TEXT = "#F2F6FA"
SECONDARY_TEXT = "#B7C3D4"
MUTED_TEXT = "#72839D"
DISABLED_TEXT = "#4C5B73"


DECISION_ACCENTS = {
    "pass": SUCCESS_GREEN,
    "manual_review": WARNING_AMBER,
    "rework": REWORK_ORANGE,
    "reject": REJECT_RED,
    "inspecting": SECONDARY_CYAN,
    "failed": FAILURE_RED,
}

STATUS_ICONS = {
    "waiting": "○",
    "running": "◌",
    "completed": "✓",
    "complete": "✓",
    "partial": "!",
    "partial success": "!",
    "failed": "!",
    "pass": "✓",
    "manual_review": "!",
    "rework": "↻",
    "reject": "×",
    "inspecting": "◌",
}


def inject_global_theme() -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            --fs-bg: {APP_BACKGROUND};
            --fs-sidebar: {SIDEBAR_BACKGROUND};
            --fs-panel: {PANEL_BACKGROUND};
            --fs-panel-elevated: {ELEVATED_PANEL};
            --fs-console: {CONSOLE_BACKGROUND};
            --fs-border: {PRIMARY_BORDER};
            --fs-border-subtle: {SUBTLE_BORDER};
            --fs-teal: {PRIMARY_TEAL};
            --fs-teal-bright: {BRIGHT_TEAL};
            --fs-cyan: {SECONDARY_CYAN};
            --fs-success: {SUCCESS_GREEN};
            --fs-warning: {WARNING_AMBER};
            --fs-rework: {REWORK_ORANGE};
            --fs-reject: {REJECT_RED};
            --fs-failure: {FAILURE_RED};
            --fs-text: {PRIMARY_TEXT};
            --fs-text-secondary: {SECONDARY_TEXT};
            --fs-text-muted: {MUTED_TEXT};
            --fs-text-disabled: {DISABLED_TEXT};
            --fs-radius: 10px;
            --fs-shadow: 0 18px 45px rgba(0, 0, 0, .34);
            --space-1: 0.25rem;
            --space-2: 0.50rem;
            --space-3: 0.75rem;
            --space-4: 1.00rem;
            --space-5: 1.25rem;
            --space-6: 1.50rem;
            --space-8: 2.00rem;
            --fs-mono: "SFMono-Regular", "Cascadia Code", "Roboto Mono", Consolas, monospace;
            --fs-sans: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }}
        .stApp {{
            background:
                radial-gradient(circle at top left, rgba(18, 214, 160, .10), transparent 32rem),
                radial-gradient(circle at top right, rgba(53, 207, 243, .08), transparent 34rem),
                var(--fs-bg);
            color: var(--fs-text);
            font-family: var(--fs-sans);
            overflow-x: hidden;
        }}
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, var(--fs-sidebar), #050a18);
            border-right: 1px solid var(--fs-border-subtle);
        }}
        section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
            padding: var(--space-4) .85rem;
        }}
        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
            gap: var(--space-2);
        }}
        [data-testid="stMainBlockContainer"],
        .block-container {{
            max-width: none;
            width: 100%;
            padding: var(--space-3) var(--space-5) var(--space-6);
        }}
        h1, h2, h3, h4, h5, h6 {{
            color: var(--fs-text);
            letter-spacing: 0;
        }}
        p, li, label, .stMarkdown, .stCaption {{
            color: var(--fs-text-secondary);
        }}
        [data-testid="stExpander"] {{
            background: rgba(12, 20, 38, .82);
            border: 1px solid var(--fs-border-subtle);
            border-radius: var(--fs-radius);
            box-shadow: none;
            margin-bottom: var(--space-2);
        }}
        [data-testid="stExpander"] summary {{
            color: var(--fs-text);
            font-weight: 750;
            letter-spacing: 0;
        }}
        .stButton > button, .stDownloadButton > button {{
            min-height: 2.55rem;
            border-radius: 8px;
            border: 1px solid var(--fs-border);
            background: rgba(16, 27, 49, .96);
            color: var(--fs-text);
            transition: border-color .16s ease, background .16s ease, transform .16s ease;
        }}
        .stButton > button:hover, .stDownloadButton > button:hover {{
            border-color: var(--fs-teal);
            color: var(--fs-text);
            background: rgba(18, 214, 160, .12);
        }}
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, var(--fs-teal), #0fa7c8);
            color: #021014;
            border-color: var(--fs-teal);
            font-weight: 850;
        }}
        .stFileUploader, .stTextInput, .stCheckbox, .stRadio {{
            color: var(--fs-text-secondary);
        }}
        div[data-testid="stMetric"] {{
            background: rgba(16, 27, 49, .86);
            border: 1px solid var(--fs-border-subtle);
            border-radius: 8px;
            padding: var(--space-3);
        }}
        div[data-testid="stMetricLabel"] p {{
            color: var(--fs-text-muted);
            font-family: var(--fs-mono);
            font-size: .75rem;
        }}
        div[data-testid="stMetricValue"] {{
            color: var(--fs-text);
            font-family: var(--fs-mono);
            font-size: 1.25rem;
        }}
        .fs-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            width: 100%;
            min-height: 76px;
            height: auto;
            padding: 0.85rem 1rem;
            margin: 0 0 0.75rem;
            overflow: visible;
            box-sizing: border-box;
            background: linear-gradient(135deg, rgba(12, 20, 38, .98), rgba(16, 27, 49, .90));
            border: 1px solid var(--fs-border);
            border-radius: var(--fs-radius);
            box-shadow: var(--fs-shadow);
        }}
        .fs-brand-kicker {{
            display: block;
            margin: 0 0 0.15rem;
            font-family: var(--fs-mono);
            color: var(--fs-teal);
            font-size: .72rem;
            line-height: 1.25;
            letter-spacing: .08em;
            text-transform: uppercase;
        }}
        .fs-brand-title {{
            display: block;
            margin: 0;
            padding: 0.08rem 0 0.12rem;
            color: var(--fs-text);
            font-size: 1.75rem;
            font-weight: 900;
            line-height: 1.18;
            overflow: visible;
        }}
        .fs-brand-subtitle {{
            display: block;
            color: var(--fs-text-secondary);
            font-size: .96rem;
            margin: 0.1rem 0 0;
            line-height: 1.35;
        }}
        .fs-header-right {{
            display: flex;
            flex-wrap: wrap;
            justify-content: flex-end;
            align-items: center;
            align-content: center;
            gap: 0.5rem;
        }}
        .fs-panel {{
            background: rgba(12, 20, 38, .88);
            border: 1px solid var(--fs-border-subtle);
            border-radius: var(--fs-radius);
            padding: var(--space-4);
            box-shadow: 0 12px 32px rgba(0, 0, 0, .22);
        }}
        .fs-panel + .fs-panel {{
            margin-top: var(--space-3);
        }}
        .fs-panel-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: var(--space-3);
            margin-bottom: var(--space-2);
            padding-bottom: var(--space-2);
            border-bottom: 1px solid var(--fs-border-subtle);
        }}
        .fs-panel-title {{
            font-family: var(--fs-mono);
            font-size: .78rem;
            text-transform: uppercase;
            letter-spacing: .08em;
            color: var(--fs-text);
        }}
        .fs-panel-meta {{
            font-family: var(--fs-mono);
            color: var(--fs-text-muted);
            font-size: .74rem;
        }}
        .fs-badge, .fs-chip {{
            display: inline-flex;
            align-items: center;
            gap: var(--space-1);
            border: 1px solid var(--fs-border);
            border-radius: 999px;
            background: rgba(16, 27, 49, .92);
            color: var(--fs-text-secondary);
            padding: .28rem var(--space-2);
            font-family: var(--fs-mono);
            font-size: .74rem;
            white-space: nowrap;
        }}
        .fs-badge strong, .fs-chip strong {{
            color: var(--fs-text);
            font-weight: 800;
        }}
        .fs-status-pass, .fs-status-completed, .fs-status-complete {{ border-color: rgba(34, 201, 131, .72); color: var(--fs-success); }}
        .fs-status-running, .fs-status-inspecting {{ border-color: rgba(53, 207, 243, .72); color: var(--fs-cyan); }}
        .fs-status-manual-review, .fs-status-partial, .fs-status-partial-success, .fs-status-waiting {{ border-color: rgba(245, 185, 66, .68); color: var(--fs-warning); }}
        .fs-status-rework {{ border-color: rgba(255, 138, 61, .72); color: var(--fs-rework); }}
        .fs-status-reject, .fs-status-failed {{ border-color: rgba(255, 77, 95, .72); color: var(--fs-reject); }}
        .fs-decision-card {{
            position: relative;
            overflow: hidden;
            background: linear-gradient(160deg, rgba(16, 27, 49, .98), rgba(2, 8, 23, .96));
            border: 1px solid var(--decision-accent, var(--fs-border));
            border-radius: var(--fs-radius);
            padding: var(--space-4);
            min-height: 300px;
            box-shadow: var(--fs-shadow);
        }}
        .fs-decision-card::before {{
            content: "";
            position: absolute;
            inset: 0 0 auto;
            height: 3px;
            background: var(--decision-accent, var(--fs-cyan));
        }}
        .fs-decision-label {{
            display: flex;
            align-items: center;
            gap: var(--space-2);
            color: var(--fs-text);
            font-size: 2rem;
            line-height: 1.02;
            font-weight: 950;
        }}
        .fs-decision-summary {{
            color: var(--fs-text-secondary);
            margin-top: var(--space-3);
            font-size: 1.02rem;
            line-height: 1.42;
        }}
        .fs-decision-action {{
            margin-top: var(--space-4);
            padding-top: var(--space-3);
            border-top: 1px solid var(--fs-border-subtle);
            color: var(--fs-text);
            font-weight: 780;
        }}
        .fs-decision-meta {{
            display: flex;
            flex-wrap: wrap;
            gap: var(--space-2);
            margin-top: var(--space-3);
        }}
        .fs-agent-card {{
            background: rgba(16, 27, 49, .74);
            border: 1px solid var(--fs-border-subtle);
            border-left: 3px solid var(--agent-accent, var(--fs-border));
            border-radius: 8px;
            padding: var(--space-3);
            min-height: 98px;
            margin-bottom: .65rem;
        }}
        .fs-agent-index {{
            color: var(--fs-text-muted);
            font-family: var(--fs-mono);
            font-size: .72rem;
            text-transform: uppercase;
        }}
        .fs-agent-role {{
            color: var(--fs-text);
            font-weight: 800;
            margin-top: var(--space-1);
            line-height: 1.2;
        }}
        .fs-agent-state {{
            color: var(--fs-text-secondary);
            font-family: var(--fs-mono);
            font-size: .78rem;
            margin-top: var(--space-2);
        }}
        .fs-console {{
            background: var(--fs-console);
            border: 1px solid var(--fs-border-subtle);
            border-radius: 8px;
            padding: var(--space-3);
            max-height: 260px;
            overflow: auto;
            font-family: var(--fs-mono);
            color: var(--fs-text-secondary);
            font-size: .82rem;
        }}
        .fs-console-entry {{ margin-bottom: .65rem; }}
        .fs-console-label {{ color: var(--fs-cyan); }}
        .fs-console-text {{ color: var(--fs-text-secondary); }}
        .fs-warning-list {{
            display: grid;
            gap: var(--space-2);
        }}
        .fs-warning-item {{
            border: 1px solid rgba(245, 185, 66, .34);
            border-left: 3px solid var(--fs-warning);
            border-radius: 8px;
            padding: .58rem var(--space-3);
            background: rgba(245, 185, 66, .08);
            color: var(--fs-text);
        }}
        .fs-image-frame {{
            background: #020817;
            border: 1px solid var(--fs-border);
            border-radius: var(--fs-radius);
            padding: .65rem;
            margin-top: var(--space-2);
            box-shadow: inset 0 0 0 1px rgba(53, 207, 243, .04);
        }}
        .fs-mode-note {{
            color: var(--fs-text-muted);
            font-family: var(--fs-mono);
            font-size: .75rem;
        }}
        [data-testid="stImage"] {{
            margin-top: var(--space-2);
        }}
        @media (max-width: 1200px) {{
            [data-testid="stMainBlockContainer"],
            .block-container {{
                padding-left: .8rem;
                padding-right: .8rem;
            }}
        }}
        @media (max-width: 800px) {{
            [data-testid="stMainBlockContainer"],
            .block-container {{
                padding: .6rem .6rem var(--space-4);
            }}
            .fs-header {{
                align-items: flex-start;
                flex-direction: column;
            }}
            .fs-header-right {{ justify-content: flex-start; }}
            .fs-decision-label {{ font-size: 1.5rem; }}
            .fs-panel {{ padding: var(--space-3); }}
        }}
        @media (prefers-reduced-motion: reduce) {{
            * {{ transition: none !important; animation: none !important; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_brand_header(
    mode: str,
    model: str | None = None,
    item_id: str | None = None,
    system_status: str = "System Ready",
) -> None:
    st.markdown(
        build_brand_header_html(mode, model, item_id, system_status),
        unsafe_allow_html=True,
    )


def build_brand_header_html(
    mode: str,
    model: str | None = None,
    item_id: str | None = None,
    system_status: str = "System Ready",
) -> str:
    model_text = model or "Gemma 4"
    item_chip = (
        f'<span class="fs-chip">ITEM <strong>{html_escape(item_id)}</strong></span>'
        if item_id
        else ""
    )
    return f"""
        <div class="fs-header">
            <div>
                <div class="fs-brand-kicker">NEURAL INSPECTION PIPELINE</div>
                <div class="fs-brand-title">FactorySwarm</div>
                <div class="fs-brand-subtitle">AI Visual Quality Inspection</div>
            </div>
            <div class="fs-header-right">
                <span class="fs-badge fs-status-running">MODE <strong>{html_escape(mode)}</strong></span>
                <span class="fs-chip">PIPELINE <strong>{html_escape(model_text)} • Cerebras</strong></span>
                <span class="fs-badge fs-status-complete">● <strong>{html_escape(system_status)}</strong></span>
                {item_chip}
            </div>
        </div>
        """


def render_status_badge(status: str, label: str | None = None) -> str:
    normalized = normalize_status(status)
    icon = STATUS_ICONS.get(status.lower(), "•")
    text = label or status.replace("_", " ").title()
    return (
        f'<span class="fs-badge fs-status-{html_escape(normalized)}">'
        f'{html_escape(icon)} <strong>{html_escape(text)}</strong></span>'
    )


def render_metric_chip(label: str, value: str | float | None, suffix: str = "") -> str:
    value_text = "—" if value is None else f"{value}{suffix}"
    return (
        f'<span class="fs-chip">{html_escape(label)} '
        f'<strong>{html_escape(value_text)}</strong></span>'
    )


def render_panel_header(title: str, meta: str | None = None) -> None:
    meta_html = (
        f'<div class="fs-panel-meta">{html_escape(meta)}</div>' if meta else ""
    )
    st.markdown(
        f"""
        <div class="fs-panel-header">
            <div class="fs-panel-title">{html_escape(title)}</div>
            {meta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_decision_card(
    decision: InspectionDecision | str,
    summary: str,
    confidence: float | None,
    human_review_required: bool | None,
    next_action: str,
) -> None:
    decision_value = decision.value if isinstance(decision, InspectionDecision) else str(decision).lower()
    accent = DECISION_ACCENTS.get(decision_value, DECISION_ACCENTS.get("inspecting", SECONDARY_CYAN))
    status_key = decision_value if decision_value in DECISION_ACCENTS else decision_value.replace(" ", "_")
    icon = STATUS_ICONS.get(status_key, "◌")
    if human_review_required is None:
        review_text = "Awaiting inspection result"
    else:
        review_text = "Human review required" if human_review_required else "Human review not required by report"
    st.markdown(
        f"""
        <div class="fs-decision-card" style="--decision-accent: {accent};">
            <div class="fs-decision-label"><span>{html_escape(icon)}</span>{html_escape(decision_label(decision))}</div>
            <div class="fs-decision-summary">{html_escape(summary)}</div>
            <div class="fs-decision-action">{html_escape(next_action)}</div>
            <div class="fs-decision-meta">
                {render_metric_chip("CONF", format_confidence(confidence))}
                {render_status_badge("manual_review" if human_review_required else "complete", review_text)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_agent_card(
    index: int,
    role: str,
    status: str,
    latency_seconds: float | None = None,
) -> None:
    status_key = normalize_status(status)
    if status_key in {"completed", "complete"}:
        accent = SUCCESS_GREEN
    elif status_key in {"running", "inspecting"}:
        accent = SECONDARY_CYAN
    elif status_key in {"failed"}:
        accent = FAILURE_RED
    elif status_key in {"partial", "partial-success"}:
        accent = WARNING_AMBER
    else:
        accent = PRIMARY_BORDER
    latency = format_seconds(latency_seconds)
    icon = STATUS_ICONS.get(status.lower(), "○")
    st.markdown(
        f"""
        <div class="fs-agent-card" style="--agent-accent: {accent};">
            <div class="fs-agent-index">AGENT {index}</div>
            <div class="fs-agent-role">{html_escape(role)}</div>
            <div class="fs-agent-state">{html_escape(icon)} {html_escape(status.replace("_", " ").title())} • {html_escape(latency)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_console_entry(label: str, text: str) -> str:
    return (
        '<div class="fs-console-entry">'
        f'<div class="fs-console-label">[{html_escape(label)}]</div>'
        f'<div class="fs-console-text">{html_escape(text)}</div>'
        "</div>"
    )


def render_console(entries: Iterable[tuple[str, str]]) -> None:
    body = "".join(render_console_entry(label, text) for label, text in entries)
    st.markdown(f'<div class="fs-console">{body}</div>', unsafe_allow_html=True)


def render_warning_list(items: list[str]) -> None:
    if not items:
        return
    body = "".join(
        f'<div class="fs-warning-item">! {html_escape(item)}</div>' for item in items
    )
    st.markdown(f'<div class="fs-warning-list">{body}</div>', unsafe_allow_html=True)


def render_performance_bar(
    parallel_seconds: float | None,
    verifier_seconds: float | None,
    total_seconds: float | None,
    sequential_seconds: float | None,
    speedup: float | None,
    successful_agents: int | None = None,
) -> None:
    chips = [
        render_metric_chip("PARALLEL", format_seconds(parallel_seconds)),
        render_metric_chip("VERIFIER", format_seconds(verifier_seconds)),
        render_metric_chip("TOTAL", format_seconds(total_seconds)),
        render_metric_chip("EST. SEQ", format_seconds(sequential_seconds)),
        render_metric_chip("EST. SPEEDUP", format_speedup(speedup)),
    ]
    if successful_agents is not None:
        chips.append(render_metric_chip("AGENTS OK", str(successful_agents)))
    st.markdown(
        '<div class="fs-header-right" style="justify-content:flex-start;margin:.5rem 0 1rem;">'
        + "".join(chips)
        + "</div>",
        unsafe_allow_html=True,
    )


def render_mode_switch() -> None:
    st.caption("Switch modes from the sidebar.")
