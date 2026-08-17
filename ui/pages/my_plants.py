"""The My Plants grid — the home surface (PLAN.md §12)."""

import streamlit as st

from core.config import get_settings
from ui import bootstrap
from ui.components.plant_photo import render_plant_photo

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

# A bordered container has no fill parameter, so the cards would sit at the page's
# own colour with only a border to separate them. ``st.container(key=…)`` renders an
# ``st-key-<key>`` class — a documented styling hook, unlike Streamlit's internal
# class names, which is why this one rule is safe where blanket CSS would not be.
# A shade down from the sage in .streamlit/config.toml, so a card reads as a surface
# lying on the page.
_CARD_KEY = "plant_card_"
_CARD_FILL = "#DFEADB"

# The card's text scales with the window; Streamlit's heading and body sizes do not.
# Moving the browser to a smaller screen narrowed the cards and their photographs
# while the name and verdict stayed the size they were, so the text set the card's
# height and the photo was left looking like a thumbnail inside it. clamp() ties the
# size to viewport width between a floor and a ceiling: it stays readable on a laptop
# and stops growing on a large monitor.
st.markdown(
    f"""<style>
    [class*="st-key-{_CARD_KEY}"] {{ background-color: {_CARD_FILL}; }}
    [class*="st-key-{_CARD_KEY}"] h4 {{
        font-size: clamp(0.9rem, 1.05vw, 1.3rem);
        margin: 0 0 0.2rem 0;
        padding: 0;
    }}
    [class*="st-key-{_CARD_KEY}"] p {{
        font-size: clamp(0.75rem, 0.8vw, 1rem);
        margin-bottom: 0.15rem;
    }}
    [class*="st-key-{_CARD_KEY}"] button p {{
        font-size: clamp(0.7rem, 0.75vw, 0.9rem);
    }}
    </style>""",
    unsafe_allow_html=True,
)

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
            # Constructed inside the `with`, not before it: a container attaches to
            # whichever container is active when it is created, so building it first
            # would put the card on the page instead of in its column.
            key = f"{_CARD_KEY}{summary.plant.id}"
            with column, st.container(border=True, height="stretch", key=key):
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

# No "Add a plant" button below the grid: adding one is what the Diagnose page in the
# sidebar is, and a second door to it only made the grid end on a stray control. The
# empty state keeps its call to action, where there is no grid and no reason yet to
# know what Diagnose does.
