class StoreError(Exception):
    """Base for expected business errors. `code` maps to a translated message."""

    code = "error_generic"


class InsufficientBalance(StoreError):
    code = "err_insufficient"

    def __init__(self, balance_cents: int, needed_cents: int):
        super().__init__(f"balance {balance_cents} < {needed_cents}")
        self.balance_cents = balance_cents
        self.needed_cents = needed_cents


class DuplicateTransaction(StoreError):
    code = "err_duplicate_txn"


class AlreadyDecided(StoreError):
    code = "err_already_decided"


class NotAvailable(StoreError):
    code = "err_not_available"


class BelowMinimum(StoreError):
    code = "err_below_min"
