"""Values the suite needs that the application refuses to default.

``jwt_secret`` has no default and a minimum length, because a generated one would log
everybody out on restart and a short one weakens the signature. Tests supply a real one
like any deployment does — this is that value, in one place so a change to the rule does
not mean editing thirty files.
"""

TEST_JWT_SECRET = "test-secret-for-the-suite-not-used-in-anger"
