from __future__ import annotations

import streamlit as st

from ui.expert_view import (
    decision_label,
    display_items,
    render_bullet_list,
    render_expert_view,
    render_final_report,
    render_performance,
    render_specialist_reports,
    render_status_cards,
    run_async,
)
from ui.operator_view import render_operator_view
from ui.state import EXPERT_MODE, OPERATOR_MODE, initialize_ui_state


def apply_pending_ui_mode() -> None:
    pending_mode = st.session_state.pop("pending_ui_mode", None)
    if pending_mode in {OPERATOR_MODE, EXPERT_MODE}:
        st.session_state.ui_mode = pending_mode


def main() -> None:
    st.set_page_config(page_title="FactorySwarm", layout="wide")
    initialize_ui_state(st.session_state)
    apply_pending_ui_mode()

    st.sidebar.radio(
        "Interface",
        [OPERATOR_MODE, EXPERT_MODE],
        key="ui_mode",
        label_visibility="collapsed",
    )

    if st.session_state.ui_mode == EXPERT_MODE:
        render_expert_view()
    else:
        render_operator_view()


if __name__ == "__main__":
    main()
