"""
validation
----------
Validates Instagram data export ZIP before analysis.
Ensures: single top-level folder 'connections', only followers_and_following with JSON files,
required files present, size within limit. Never raises — returns (ok, errors).
"""

from .validator import validate_zip

__all__ = ["validate_zip"]
