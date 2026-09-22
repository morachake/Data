"""Diagnose which shortlist filter emptied the result set."""

import pandas as pd
import streamlit as st


def show_filter_funnel(df: pd.DataFrame, filters: list[tuple[str, callable]]):
    """filters: ordered list of (label, fn(df) -> boolean Series)."""
    rows = [("All players in mart", len(df))]
    current = df
    for label, fn in filters:
        current = current[fn(current)]
        rows.append((label, len(current)))

    if len(current) > 0:
        return current

    funnel = pd.DataFrame(rows, columns=["Filter applied", "Players remaining"])
    zero_step = funnel[funnel["Players remaining"] == 0].iloc[0]["Filter applied"]
    st.warning(f"No players left after: **{zero_step}**. Relax that filter first.")
    st.dataframe(funnel, hide_index=True, width="stretch")
    return None
