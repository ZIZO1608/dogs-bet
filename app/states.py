from aiogram.fsm.state import State, StatesGroup


class TopupFlow(StatesGroup):
    amount = State()
    txn_ref = State()
    proof = State()


class WithdrawFlow(StatesGroup):
    method = State()
    amount = State()
    destination = State()


class CreateAccountFlow(StatesGroup):
    username = State()


class GiftFlow(StatesGroup):
    code = State()


class AdminFlow(StatesGroup):
    custom_credit = State()
    reject_note = State()
    reject_order_note = State()  # kept for old order flow
    find_user = State()
    adjust_balance = State()
    broadcast = State()
    syp_rate = State()
    method_details = State()
    gift_create = State()
    new_game = State()
    new_package = State()
    package_price = State()
