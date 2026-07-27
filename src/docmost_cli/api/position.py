"""Fractional index generation for Docmost page ordering.

Docmost orders sibling pages by a base62 fractional index string and enforces
``@IsString @MinLength(5) @MaxLength(12)`` on ``POST /api/pages/move``. Its
frontend feeds these keys back into the JavaScript ``fractional-indexing``
generator, which validates them — so a malformed key makes the web editor
throw when a user later drags a sibling next to a CLI-placed page. This module
therefore ports the reference algorithm rather than approximating it.

The reference algorithm's shortest key is ``"a0"`` (2 characters), which the
server would reject, so generated keys are padded with random digits. Padding
only ever appends, and every append is checked to keep the key strictly below
its upper bound.

This module is standalone: it imports nothing from the rest of the project.
"""

import math
import random

__all__ = [
    "DIGITS",
    "MAX_POSITION_LEN",
    "MIN_POSITION_LEN",
    "PositionError",
    "generate_key_between",
    "is_valid_position",
]

# Base62, in ASCII collation order so plain string comparison sorts correctly.
DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

MIN_POSITION_LEN = 5
MAX_POSITION_LEN = 12

_ZERO = DIGITS[0]


class PositionError(ValueError):
    """Raised when a position key cannot be generated or is malformed."""


def _integer_length(head: str) -> int:
    """Return the length of the integer part given its leading character."""
    if "a" <= head <= "z":
        return ord(head) - ord("a") + 2
    if "A" <= head <= "Z":
        return ord("Z") - ord(head) + 2
    raise PositionError(f"invalid order key head: {head!r}")


def _integer_part(key: str) -> str:
    """Return the integer part of an order key."""
    if not key:
        raise PositionError("empty order key")
    length = _integer_length(key[0])
    if length > len(key):
        raise PositionError(f"invalid order key: {key!r}")
    return key[:length]


def _validate_integer(value: str) -> None:
    if len(value) != _integer_length(value[0]):
        raise PositionError(f"invalid integer part of order key: {value!r}")


def _validate_order_key(key: str) -> None:
    if key == "A" + _ZERO * 26:
        raise PositionError(f"invalid order key: {key!r}")
    integer = _integer_part(key)
    fraction = key[len(integer) :]
    if fraction.endswith(_ZERO):
        raise PositionError(f"invalid order key: {key!r}")


def _midpoint(a: str, b: str | None) -> str:
    """Return a string strictly between ``a`` and ``b``.

    ``a`` may be empty (meaning "smallest"); ``b`` may be None (meaning
    "largest"). Neither input nor output may end with the zero digit.
    """
    if b is not None and a >= b:
        raise PositionError(f"{a!r} >= {b!r}")
    if a.endswith(_ZERO) or (b is not None and b.endswith(_ZERO)):
        raise PositionError("trailing zero")

    if b is not None:
        # Strip the longest common prefix, padding `a` with zeros as we go.
        n = 0
        while n < len(b) and (a[n] if n < len(a) else _ZERO) == b[n]:
            n += 1
        if n > 0:
            return b[:n] + _midpoint(a[n:], b[n:])

    digit_a = DIGITS.index(a[0]) if a else 0
    digit_b = DIGITS.index(b[0]) if b else len(DIGITS)

    if digit_b - digit_a > 1:
        # Room for a digit strictly between the two.
        mid = math.floor(0.5 * (digit_a + digit_b) + 0.5)
        return DIGITS[mid]

    # First digits are consecutive.
    if b is not None and len(b) > 1:
        return b[:1]
    return DIGITS[digit_a] + _midpoint(a[1:], None)


def _increment_integer(value: str) -> str | None:
    """Return the next integer part, or None if the space is exhausted."""
    _validate_integer(value)
    head, digs = value[0], list(value[1:])
    carry = True
    for i in range(len(digs) - 1, -1, -1):
        if not carry:
            break
        d = DIGITS.index(digs[i]) + 1
        if d == len(DIGITS):
            digs[i] = DIGITS[0]
        else:
            digs[i] = DIGITS[d]
            carry = False
    if carry:
        if head == "Z":
            return "a" + DIGITS[0]
        if head == "z":
            return None
        h = chr(ord(head) + 1)
        if h > "a":
            digs.append(DIGITS[0])
        else:
            digs.pop()
        return h + "".join(digs)
    return head + "".join(digs)


def _decrement_integer(value: str) -> str | None:
    """Return the previous integer part, or None if the space is exhausted."""
    _validate_integer(value)
    head, digs = value[0], list(value[1:])
    borrow = True
    for i in range(len(digs) - 1, -1, -1):
        if not borrow:
            break
        d = DIGITS.index(digs[i]) - 1
        if d == -1:
            digs[i] = DIGITS[-1]
        else:
            digs[i] = DIGITS[d]
            borrow = False
    if borrow:
        if head == "a":
            return "Z" + DIGITS[-1]
        if head == "A":
            return None
        h = chr(ord(head) - 1)
        if h < "Z":
            digs.append(DIGITS[-1])
        else:
            digs.pop()
        return h + "".join(digs)
    return head + "".join(digs)


def _key_between(a: str | None, b: str | None) -> str:
    """Reference fractional-index key generation (no length padding)."""
    if a is not None:
        _validate_order_key(a)
    if b is not None:
        _validate_order_key(b)
    if a is not None and b is not None and a >= b:
        raise PositionError(f"{a!r} >= {b!r}")

    if a is None:
        if b is None:
            return "a" + DIGITS[0]
        int_b = _integer_part(b)
        frac_b = b[len(int_b) :]
        if int_b == "A" + _ZERO * 26:
            return int_b + _midpoint("", frac_b)
        if int_b < b:
            return int_b
        decremented = _decrement_integer(int_b)
        if decremented is None:
            raise PositionError("cannot decrement any more")
        return decremented

    if b is None:
        int_a = _integer_part(a)
        frac_a = a[len(int_a) :]
        incremented = _increment_integer(int_a)
        return int_a + _midpoint(frac_a, None) if incremented is None else incremented

    int_a = _integer_part(a)
    frac_a = a[len(int_a) :]
    int_b = _integer_part(b)
    frac_b = b[len(int_b) :]
    if int_a == int_b:
        return int_a + _midpoint(frac_a, frac_b)
    incremented = _increment_integer(int_a)
    if incremented is None:
        raise PositionError("cannot increment any more")
    if incremented < b:
        return incremented
    return int_a + _midpoint(frac_a, None)


def _pad(key: str, upper: str | None, rng: random.Random) -> str:
    """Extend ``key`` to the server's minimum length, keeping it below ``upper``.

    Appending characters only ever makes a string larger, so the lower bound is
    never at risk. The upper bound is: if ``upper`` starts with ``key``, the
    next character must be smaller than the one ``upper`` has at that position;
    otherwise ``key`` and ``upper`` already differ at an earlier index and any
    append is safe.
    """
    while len(key) < MIN_POSITION_LEN or key.endswith(_ZERO):
        if upper is not None and upper.startswith(key):
            ceiling = DIGITS.index(upper[len(key)])
            # Only digits strictly below the ceiling keep us under `upper`.
            # A ceiling of 0 or 1 leaves only the zero digit; appending it
            # keeps the key below `upper` and the loop continues one level
            # deeper (`upper` never ends with a zero digit, so it has more
            # characters to spare).
            key += _ZERO if ceiling < 2 else rng.choice(DIGITS[1:ceiling])
        else:
            key += rng.choice(DIGITS[1:])
    return key


def _generate_padded(a: str | None, b: str | None, rng: random.Random) -> str:
    """Generate a key between the bounds and extend it to the minimum length."""
    plain = _key_between(a, b)
    needs_padding = len(plain) < MIN_POSITION_LEN or plain.endswith(_ZERO)

    # Prepending returns b's integer part with an empty fraction. Padding that
    # bisects downward inside b's fraction, so repeated prepends grow the key
    # until it blows the 12-character ceiling. Stepping the integer part down
    # instead — which is what the unpadded algorithm would do on the *next*
    # prepend — yields a fresh, short slot below b with room for free jitter.
    if a is None and b is not None and needs_padding and plain == _integer_part(b):
        stepped = _decrement_integer(plain)
        if stepped is not None:
            # `stepped` differs from b within b's integer part, so appending
            # can never push it up to or past b.
            return _pad(stepped, None, rng)

    return _pad(plain, b, rng)


def generate_key_between(
    a: str | None,
    b: str | None,
    *,
    rng: random.Random | None = None,
) -> str:
    """Generate an ordering key strictly between ``a`` and ``b``.

    Args:
        a: Lower bound key, or None for "before everything".
        b: Upper bound key, or None for "after everything".
        rng: Random source for padding. Inject for deterministic tests.

    Returns:
        A key satisfying ``a < key < b`` and Docmost's 5-12 character limit.

    Raises:
        PositionError: If the bounds are invalid or too tightly packed to fit
            a key within the server's length limit.
    """
    source = rng if rng is not None else random.Random()
    key = _generate_padded(a, b, source)

    # Belt and braces: an explicit check rather than `assert`, which vanishes
    # under `python -O`.
    if (a is not None and key <= a) or (b is not None and key >= b):
        raise PositionError(f"generated key {key!r} is not between {a!r} and {b!r}")
    if len(key) > MAX_POSITION_LEN:
        raise PositionError(f"generated key {key!r} exceeds the {MAX_POSITION_LEN}-character limit")
    return key


def is_valid_position(value: str) -> bool:
    """Return True if ``value`` satisfies Docmost's position constraints."""
    return MIN_POSITION_LEN <= len(value) <= MAX_POSITION_LEN and all(
        char in DIGITS for char in value
    )
