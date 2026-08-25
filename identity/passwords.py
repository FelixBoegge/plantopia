"""Password hashing.

argon2id at the library's defaults, which track current guidance. Tuning the cost
parameters by hand would mean a number chosen once from a blog post and never revisited,
which is worse than a maintained default because it looks deliberate.

Nothing here logs, returns, or stores a password. The only value that leaves is a hash.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# A hash no password produces. Used for the seeded owner, which predates accounts and must
# never become one, and as the value compared against when an address has no account —
# see `verify`.
UNUSABLE = "!unusable"

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """The argon2id hash of a password.

    Salted per call, so two accounts choosing the same password store different values —
    which is what stops a stolen database revealing that they match.
    """
    return _hasher.hash(password)


def verify(password: str, password_hash: str) -> bool:
    """Whether a password produces this hash.

    Returns ``False`` rather than raising for a malformed or unusable hash. The caller is
    a sign-in path, and the difference between "wrong password" and "this row cannot be
    signed in to" is not one an unauthenticated caller should be able to observe.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Whether a stored hash was made with weaker parameters than the current defaults.

    Rehashing on next sign-in is how a cost increase reaches accounts that already exist:
    the plaintext is only available at that moment, and never again.
    """
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False
