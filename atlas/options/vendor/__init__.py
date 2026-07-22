"""VENDORED options math (2026-07-09) from the owner's options project
(C:/path/to/options-project @ version 0.2.0) - the tradier_data.py vendoring
precedent. Files: blackscholes.py + volatility.py copied VERBATIM except for one import line
each (app.models -> atlas.options.vendor.models); models.py is a minimal shim of the three
imported shapes. The originals are textbook-correct BSM (verified against Hull values,
put-call parity, IV round-trip - tests ported to tests/test_options_vendor_math.py).
Do NOT edit the math here; new math goes in atlas/options/math.py on top of these primitives.
"""
