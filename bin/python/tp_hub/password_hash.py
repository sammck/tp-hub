#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Password hashing using bcrypt.  Compatible with htpasswd
"""

from __future__ import annotations

import bcrypt

from .internal_types import *
#from .pkg_logging import logger

def hash_username_password(username: str, password: str) -> str:
    """
    Hash a username/password using bcrypt, in a format compatible with htpasswd.

    Returns a string in the format "{username}:{bcrypt_hash}"
    """
    # Note: The salt is more than just random data; it also includes the bcrypt
    # algorithm identifier and the number of rounds. The number of rounds is adjusted
    # periodically to keep up with the increasing speed of hardware. Currently the default
    # in bcrypt.gensalt() is 12 rounds.
    # the prefix passed to gensalt() is the bcrypt algorithm identifier, which is "2b"
    # by default. The "2" indicates the algorithm version.
    salt = bcrypt.gensalt()
    bin_cleartext = password.encode("utf-8")
    bin_hashed = bcrypt.hashpw(bin_cleartext, salt)
    hashed_str = bin_hashed.decode("utf-8")
    result = f"{username}:{hashed_str}"
    return result

def check_username_password(hashed: str, username: str, password: str) -> bool:
    """
    Check a username/password against a hash in the format "{username}:{bcrypt_hash}".
    """
    if not ':' in hashed:
        raise HubError("Invalid hashed password: missing ':'")
    encoded_username, hashed_str = hashed.split(":", 1)
    if encoded_username != username:
        return False
    bin_hashed = hashed_str.encode("utf-8")
    bin_cleartext = password.encode("utf-8")
    result = bcrypt.checkpw(bin_cleartext, bin_hashed)
    return result
