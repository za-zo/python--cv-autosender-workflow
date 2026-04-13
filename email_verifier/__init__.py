"""
Email Verifier Package
======================
Checks an email address through multiple steps before generating an AI message
or sending via Gmail — saving tokens and Gmail quota.

Usage:
    from email_verifier import EmailVerifier

    verifier = EmailVerifier()
    if verifier.check("someone@company.com"):
        # generate AI message + send Gmail
    else:
        # skip — 0 tokens, 0 Gmail quota used
"""

from email_verifier.verifier import EmailVerifier
from email_verifier.runner import EmailRunner

__all__ = ["EmailVerifier", "EmailRunner"]
