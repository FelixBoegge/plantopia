"""Who may read the evaluation results.

One protected resource, one rule, and — temporarily — one deployment switch. The tests
below pin both states, because the switch exists to be turned off again and the default
is what a deployment inherits by not deciding.
"""

from identity.roles import ADMIN, MEMBER, may_read_evaluations


def test_an_administrator_may_read_them():
    assert may_read_evaluations(ADMIN) is True


def test_an_ordinary_member_may_not_by_default():
    """The default is the deployed policy. A permissive default is the kind of thing that
    ships because nobody had a reason to tighten it."""
    assert may_read_evaluations(MEMBER) is False


def test_an_unknown_role_is_refused():
    """The only ways to acquire one are a manual database edit and a broken migration.
    Neither should widen what anybody can see."""
    assert may_read_evaluations("wizard") is False


def test_a_deployment_may_open_them_to_members():
    """Temporary, for the capstone review: the reviewer registers an ordinary account and
    has to be able to see the harness's numbers. Switched on in `.env` rather than changed
    here, so that re-locking is deleting a line of configuration rather than remembering to
    revert a line of code — see `docs/deployment-readiness.md`.
    """
    assert may_read_evaluations(MEMBER, open_to_members=True) is True


def test_opening_them_to_members_still_refuses_an_unknown_role():
    """The switch widens the rule to *members*, not to anybody. A role nobody recognises is
    no more legitimate for having been asked twice."""
    assert may_read_evaluations("wizard", open_to_members=True) is False
