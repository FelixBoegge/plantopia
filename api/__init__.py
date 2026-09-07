"""The HTTP interface.

The only client of ``services/``. Routers depend on services and never on repositories —
the one deliberate exception is serving a photograph, which needs the blob store because
no service owns image bytes.
"""
