"""Who a person is, and how a request proves it.

Kept out of ``api/`` because none of it is about HTTP: hashing, token issue and
verification, and the rules for rotation and revocation are the same whatever presents
them. The routers are a thin layer over this.
"""
