"""Failure classes that distinguish known errors from uncertain external outcomes."""

class BudgetExceeded(RuntimeError):
    """A request was not sent because the conservative token reservation did not fit."""


class ProviderOutcomeUnknown(RuntimeError):
    """A provider request was started but its final outcome could not be confirmed."""


class NativeOutcomeUnknown(RuntimeError):
    """A native tool call started but its final execution outcome could not be confirmed."""
