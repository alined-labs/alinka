"""Hypothesis profiles: `ci` (200 examples) by default, `dev` for quick local runs."""

import os

from hypothesis import settings

settings.register_profile("ci", max_examples=200, deadline=None, print_blob=True)
settings.register_profile("dev", max_examples=30, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))
