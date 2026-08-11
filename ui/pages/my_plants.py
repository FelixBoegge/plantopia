"""The My Plants grid — the home surface (PLAN.md §12)."""

import streamlit as st

from ui import bootstrap

st.title("🌿 My Plants")

service = bootstrap.get_plant_service()
summaries = service.list_plants()

if not summaries:
    st.write("No plants yet. Start your first diagnosis to add one.")
    if st.button("Diagnose a plant"):
        st.switch_page("ui/pages/diagnose.py")
else:
    pending_total = sum(s.pending_step_count for s in summaries)
    if pending_total:
        st.caption(f"{pending_total} roadmap step(s) due across your plants.")

    columns = st.columns(3)
    for index, summary in enumerate(summaries):
        with columns[index % 3], st.container(border=True):
            st.markdown(f"**{summary.plant.name}**")
            diagnosis = summary.latest_diagnosis
            if diagnosis is not None and not diagnosis.differential.is_healthy:
                st.caption(f"⚠️ {diagnosis.differential.primary.name}")
            elif diagnosis is not None:
                st.caption("🟢 Healthy")
            else:
                st.caption("No diagnosis yet")

            if summary.pending_step_count:
                st.caption(f"{summary.pending_step_count} step(s) pending")

            if st.button("View", key=f"view_{summary.plant.id}"):
                st.session_state.selected_plant_id = summary.plant.id
                st.switch_page("ui/pages/plant_detail.py")

    if st.button("Add a plant"):
        st.switch_page("ui/pages/diagnose.py")
