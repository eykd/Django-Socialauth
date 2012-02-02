# -*- coding: utf-8 -*-
"""socialauth.helpers -- helper utility functions for socialauth
"""
import hashlib
import base64


def sign(s, secret):
    """Sign a string with a secret using its base64-encoded SHA1.
    """
    return uri_b64encode(hashlib.sha1(s+secret).digest())


def uri_b64encode(s):
    return base64.urlsafe_b64encode(s).strip('=')


def uri_b64decode(s):
    return base64.urlsafe_b64decode(s + '=' * (4 - len(s) % 4))
