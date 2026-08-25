"""The HTTP interface.

A second client of ``services/``, alongside Streamlit rather than instead of it. Routers
depend on services and never on repositories — the one deliberate exception is serving a
photograph, which needs the blob store because no service owns image bytes.
"""
