"""ATLAS - Autonomous Trading, Layered Authority System.

Deterministic orchestrator that calls two stateless local LLMs (an analyst and an
adversarial auditor) as untrusted proposal generators. All execution authority lives
in deterministic code; no model component can place an order or relax a risk limit.

See docs/ for the specification and config/ for the machine-readable rules.
"""

__version__ = "0.1.0"
