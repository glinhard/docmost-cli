"""Tests for fractional-index position generation."""

import random

import pytest

from docmost_cli.api.position import (
    DIGITS,
    MAX_POSITION_LEN,
    MIN_POSITION_LEN,
    PositionError,
    generate_key_between,
    is_valid_position,
)


def _assert_well_formed(key: str) -> None:
    assert MIN_POSITION_LEN <= len(key) <= MAX_POSITION_LEN, key
    assert all(char in DIGITS for char in key), key
    assert not key.endswith(DIGITS[0]), key


class TestGenerateKeyBetween:
    def test_between_none_none_is_valid(self) -> None:
        key = generate_key_between(None, None, rng=random.Random(0))
        _assert_well_formed(key)
        assert is_valid_position(key)

    @pytest.mark.parametrize(
        ("a", "b"),
        [
            (None, "a0V8f"),
            ("a0V8f", None),
            ("a0V8f", "a0V8g"),
            ("a0", "a0V"),
            ("a0", "a00001"),
            ("a1", "a2"),
            ("Zz", "a0V8f"),
            ("Yzz", "Z0AAA"),
            ("a0V8f", "a1"),
            (None, "Z0AAA"),
        ],
    )
    def test_strictly_between(self, a: str | None, b: str | None) -> None:
        for seed in range(20):
            key = generate_key_between(a, b, rng=random.Random(seed))
            _assert_well_formed(key)
            if a is not None:
                assert a < key, f"{a!r} !< {key!r}"
            if b is not None:
                assert key < b, f"{key!r} !< {b!r}"

    def test_rejects_reversed_bounds(self) -> None:
        with pytest.raises(PositionError):
            generate_key_between("a2AAA", "a1AAA")

    @pytest.mark.parametrize("bound", ["!!!!!", "zzzzz", "a0V80", "0abcd"])
    def test_rejects_malformed_bound(self, bound: str) -> None:
        with pytest.raises(PositionError):
            generate_key_between(bound, None)

    def test_raises_when_key_space_exhausted(self) -> None:
        """A 27-character integer part cannot fit in the server's 12-char limit."""
        with pytest.raises(PositionError):
            generate_key_between(None, "A" + "0" * 25 + "1")

    def test_sequential_appends_sort_ascending(self) -> None:
        """The `last` placement path: repeatedly append after the maximum."""
        rng = random.Random(7)
        keys: list[str] = []
        previous: str | None = None
        for _ in range(500):
            key = generate_key_between(previous, None, rng=rng)
            _assert_well_formed(key)
            keys.append(key)
            previous = key
        assert keys == sorted(keys)
        assert len(set(keys)) == len(keys)

    def test_sequential_prepends_sort_descending(self) -> None:
        """The `first` placement path: repeatedly insert before the minimum."""
        rng = random.Random(11)
        keys: list[str] = []
        following: str | None = None
        for _ in range(200):
            key = generate_key_between(None, following, rng=rng)
            _assert_well_formed(key)
            keys.append(key)
            following = key
        assert keys == sorted(keys, reverse=True)

    def test_randomized_ordering_property(self) -> None:
        """Insert at random positions; the list must stay strictly ascending."""
        rng = random.Random(1234)
        keys = [generate_key_between(None, None, rng=rng)]
        for _ in range(500):
            index = rng.randrange(len(keys) + 1)
            lower = keys[index - 1] if index > 0 else None
            upper = keys[index] if index < len(keys) else None
            try:
                key = generate_key_between(lower, upper, rng=rng)
            except PositionError:
                # Legitimate exhaustion: the 12-character ceiling was hit.
                continue
            _assert_well_formed(key)
            keys.insert(index, key)
            assert keys == sorted(keys)
            assert len(set(keys)) == len(keys)

    def test_deterministic_under_seeded_rng(self) -> None:
        first = generate_key_between("a1AAA", "a2AAA", rng=random.Random(42))
        second = generate_key_between("a1AAA", "a2AAA", rng=random.Random(42))
        assert first == second

    def test_jitter_varies_across_seeds(self) -> None:
        keys = {generate_key_between(None, None, rng=random.Random(s)) for s in range(20)}
        assert len(keys) > 1


class TestIsValidPosition:
    @pytest.mark.parametrize("value", ["a0V8f", "aaaaa", "a" * MAX_POSITION_LEN])
    def test_accepts_valid(self, value: str) -> None:
        assert is_valid_position(value) is True

    @pytest.mark.parametrize("value", ["a0V", "", "a" * 13, "a0V8-", "a0V8 "])
    def test_rejects_invalid(self, value: str) -> None:
        assert is_valid_position(value) is False
