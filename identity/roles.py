"""What an account may reach, as distinct from what it may spend.

Two values. ``member`` is everybody; ``admin`` is whoever runs the deployment. There is one
protected resource — the evaluation results — and it is protected because it is the one
thing in the system that nobody owns, so tenancy has nothing to say about it.

**A refusal here is 404, not 403.** The same reasoning as everywhere else: a response that
distinguishes "you may not" from "there is nothing here" tells a stranger what exists.

Deliberately not a permission system. No groups, no policies, no resource-action pairs — a
column with a default, and one check. When a second protected thing appears, this is small
enough to replace rather than large enough to have to extend.
"""

MEMBER = "member"
ADMIN = "admin"

ROLES = frozenset({MEMBER, ADMIN})


def may_read_evaluations(role: str, *, open_to_members: bool = False) -> bool:
    """Whether an account may see the harness's results.

    Unknown roles are refused, in both states. A role nobody recognises is not a reason to
    grant access — and the only way to acquire one is a manual database edit or a migration
    that went wrong, neither of which should widen what anybody can see.

    ``open_to_members`` is **temporary**, and carried by configuration rather than written
    into this rule. The capstone reviewer registers an ordinary account and has to be able
    to reach the numbers; wiring that as a code change would mean remembering to revert it
    before a deployment, and the thing most likely to be forgotten is the thing that opens
    a protected resource. As configuration, the secure state is what a deployment inherits
    by saying nothing, and re-locking is deleting a line from `.env`.
    ``docs/deployment-readiness.md`` carries the task either way.

    Defaulted rather than required so that every existing caller and test keeps asking the
    deployed question — which is the one worth being the default.
    """
    if role == ADMIN:
        return True
    return open_to_members and role in ROLES
