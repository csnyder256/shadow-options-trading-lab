"""Post-pivot (2026-07-10, all-in options): the equity order machinery (broker adapters,
order lifecycle, guardian, reconcile, sim) is ARCHIVED under attic\\atlas\\execution\\.
One module remains - the stdlib-only `rate_gate`, a pure request-pacing helper with no
network code. The broker MCP auth/transport that used to sit beside it is excluded from
this public copy, so no order transport ships at all. The OPTIONS platform never
imports this package (pinned by tests\\test_keep_imports.py); nothing here is on any
decision path. Archived names resolve lazily or fail loud with a pointer."""

_ARCHIVED = {
    "Account": "broker_adapter", "BrokerAdapter": "broker_adapter",
    "Capabilities": "broker_adapter", "Fill": "broker_adapter", "Order": "broker_adapter",
    "OrderLeg": "broker_adapter", "OrderRequest": "broker_adapter",
    "OrderSide": "broker_adapter", "OrderStatus": "broker_adapter",
    "OrderType": "broker_adapter", "Position": "broker_adapter", "Quote": "broker_adapter",
    "TimeInForce": "broker_adapter",
    "OverfillError": "order_state", "make_client_order_id": "order_state",
    "SimBrokerAdapter": "sim_adapter",
    "Divergence": "reconcile", "reconcile": "reconcile",
    "LifecycleEvent": "order_lifecycle", "LifecycleState": "order_lifecycle",
    "OrderLifecycleManager": "order_lifecycle", "PendingOrder": "order_lifecycle",
}

__all__: list = []


def __getattr__(name: str):  # PEP 562 - archived order machinery resolves lazily or fails loud
    if name in _ARCHIVED:
        sub = _ARCHIVED[name]
        try:
            import importlib

            mod = importlib.import_module(f"atlas.execution.{sub}")
        except ImportError as exc:
            raise ImportError(
                f"atlas.execution.{name} belongs to the ARCHIVED equity order machinery "
                f"(attic\\atlas\\execution\\{sub}.py - see attic\\ARCHIVE_MANIFEST.md)"
            ) from exc
        # the submodule import sets the package attribute `sub` to the MODULE; when a
        # function shares its module's name (reconcile), rebind the function over it
        if sub in _ARCHIVED and _ARCHIVED[sub] == sub:
            globals()[sub] = getattr(mod, sub)
        val = getattr(mod, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module 'atlas.execution' has no attribute {name!r}")
