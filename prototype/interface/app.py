"""PROTOTYPE. Three variants of the ENGR 689 slide-study interface.

Question: Streamlit or Gradio, and what is actually on the screen while a run is
happening? Three structurally different answers, switchable via `?variant=A|B|C`
and the floating bar at the bottom of the page.

Throwaway. No pipeline behind it, no network, no persistence. The only real
thing is the page render, which comes from the committed Day 3 deck.

Run:  streamlit run prototype/interface/app.py
"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import variant_a  # noqa: E402
import variant_b  # noqa: E402
import variant_c  # noqa: E402
from shared import VARIANTS, current_variant, init_state, reset_run, switcher_bar  # noqa: E402

st.set_page_config(page_title="PROTOTYPE slide study agent", layout="wide")
init_state()

with st.sidebar:
    st.markdown("### Prototype controls")
    st.caption("Not part of any variant. Delete when this is folded into the real app.")
    st.session_state.speed = st.select_slider(
        "Fake run speed", options=[0.001, 0.005, 0.02, 0.06, 0.15],
        value=st.session_state.speed,
        format_func=lambda v: {0.001: "instant", 0.005: "fast", 0.02: "demo",
                               0.06: "slow", 0.15: "very slow"}[v],
    )
    if st.button("Reset run"):
        reset_run()
        st.rerun()
    st.divider()
    for key, name in VARIANTS.items():
        st.markdown(f"[{key} - {name}](?variant={key})")

variant = current_variant()
{"A": variant_a, "B": variant_b, "C": variant_c}[variant].render()
switcher_bar()
