"""Utilities for detecting overlap between adjacent text chunks."""

from collections.abc import Callable

_SMALL_OVERLAP_TOKEN_LIMIT = 50


def overlap_prefix_chars(
    previous: str,
    current: str,
    chunk_overlap: int,
    count_tokens: Callable[[str], int],
) -> int:
    """Return the character count shared by the previous suffix and current prefix.

    The overlap is capped by ``chunk_overlap`` tokens. Small configured
    overlaps use direct string comparisons; larger overlaps use KMP.
    """
    if chunk_overlap <= 0 or not previous or not current:
        return 0

    if chunk_overlap <= _SMALL_OVERLAP_TOKEN_LIMIT:
        return _overlap_prefix_chars_by_strings(
            previous, current, chunk_overlap, count_tokens
        )

    return _overlap_prefix_chars_by_kmp(previous, current, chunk_overlap, count_tokens)


def _overlap_prefix_chars_by_strings(
    previous: str,
    current: str,
    chunk_overlap: int,
    count_tokens: Callable[[str], int],
) -> int:
    """Find the longest valid overlap by checking candidate substrings."""
    for length in range(min(len(previous), len(current)), 0, -1):
        if previous[-length:] != current[:length]:
            continue
        if count_tokens(current[:length]) <= chunk_overlap:
            return length
    return 0


def _overlap_prefix_chars_by_kmp(
    previous: str,
    current: str,
    chunk_overlap: int,
    count_tokens: Callable[[str], int],
) -> int:
    """Find the longest valid overlap with KMP substring matching."""
    # Find the longest ``previous`` suffix equal to a ``current`` prefix.
    prefix = [0] * len(current)
    matched = 0
    for i in range(1, len(current)):
        while matched and current[i] != current[matched]:
            matched = prefix[matched - 1]
        if current[i] == current[matched]:
            matched += 1
        prefix[i] = matched

    matched = 0
    for char in previous:
        while matched and (matched == len(current) or char != current[matched]):
            matched = prefix[matched - 1]
        if char == current[matched]:
            matched += 1

    # Avoid treating ordinary repeated text as split overlap when it exceeds
    # the configured token overlap.
    while matched and count_tokens(current[:matched]) > chunk_overlap:
        matched = prefix[matched - 1]
    return matched
