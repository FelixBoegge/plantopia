"""The My Plants grid — the home surface (PLAN.md §12)."""

import streamlit as st

from core.config import get_settings
from ui import bootstrap
from ui.components.plant_photo import render_plant_photo
from ui.components.profile_panel import render_profile_panel

st.title("🌿 My Plants")

service = bootstrap.get_plant_service()
summaries = service.list_plants()
upload_dir = get_settings().upload_path

# Three across. The photo is portrait (ui/components/plant_photo.py) and sits beside
# the details rather than above them, so a card needs roughly twice the width of the
# image itself — four across left them too slim to read.
_CARDS_PER_ROW = 3

# Photo column to details column, half and half: the photograph is the point of the
# card, and the name, verdict and button are a caption to it.
_CARD_SPLIT = (1, 1)

if not summaries:
    st.write("No plants yet. Start your first diagnosis to add one.")
    if st.button("Diagnose a plant"):
        st.switch_page("ui/pages/diagnose.py")
else:
    pending_total = sum(s.pending_step_count for s in summaries)
    if pending_total:
        st.caption(f"{pending_total} roadmap step(s) due across your plants.")

    # One st.columns() call per row, rather than one shared row indexed by modulo:
    # a shared row stacks the fourth card underneath the first inside the same
    # column instead of starting a row, which is what made the grid look ragged.
    for start in range(0, len(summaries), _CARDS_PER_ROW):
        row = summaries[start : start + _CARDS_PER_ROW]
        columns = st.columns(_CARDS_PER_ROW)
        for column, summary in zip(columns, row, strict=False):
            # height="stretch" fills the column, and columns in one row are as tall
            # as the tallest among them — so cards match without anyone picking a
            # pixel height that a longer candidate name would then overflow.
            with column, st.container(border=True, height="stretch"):
                photo, details = st.columns(_CARD_SPLIT)
                with photo:
                    render_plant_photo(summary.plant.photo_ref, upload_dir)
                with details:
                    # A heading for the name and body text for the rest, rather than
                    # bold-and-caption: the details share half a card with a photo,
                    # and caption-sized text was hard to read across the grid. Sized
                    # with markdown rather than injected CSS so it stays legible to
                    # anyone reading this page and cannot break on a Streamlit
                    # class-name change.
                    st.markdown(f"#### {summary.plant.name}")
                    diagnosis = summary.latest_diagnosis
                    if diagnosis is not None and not diagnosis.differential.is_healthy:
                        st.markdown(f"⚠️ {diagnosis.differential.primary.name}")
                    elif diagnosis is not None:
                        st.markdown("🟢 Healthy")
                    else:
                        st.markdown("No diagnosis yet")

                    if summary.pending_step_count:
                        st.markdown(f"{summary.pending_step_count} step(s) pending")

                    if st.button("View", key=f"view_{summary.plant.id}", width="stretch"):
                        st.session_state.selected_plant_id = summary.plant.id
                        st.switch_page("ui/pages/plant_detail.py")

    if st.button("Add a plant"):
        st.switch_page("ui/pages/diagnose.py")

with st.expander("What Plantopia has learned about you"):
    profile = bootstrap.get_profile_service()
    render_profile_panel(profile.all_facts(), profile.forget)
