import pytest
import pytest_asyncio

from app.db import create_tables, make_engine, make_sessionmaker
from app.models import Currency, Game, Package, PaymentMethod, Status, User
from app.money import parse_usd_to_cents, syp_to_usd_cents
from app.services import deposits, orders, wallet
from app.services.errors import AlreadyDecided, BelowMinimum, DuplicateTransaction, InsufficientBalance

USER = 111
ADMIN = 999
RATE = 13000.0


@pytest_asyncio.fixture
async def sm(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await create_tables(engine)
    maker = make_sessionmaker(engine)
    async with maker() as s:
        s.add(User(id=USER, full_name="Test"))
        game = Game(name_ar="ببجي", name_en="PUBG Mobile")
        s.add(game)
        await s.flush()
        s.add(Package(game_id=game.id, title="60 UC", price_cents=99))
        s.add(Package(game_id=game.id, title="325 UC", price_cents=499))
        s.add(PaymentMethod(code="sham_usd", name_ar="شام كاش $", name_en="ShamCash $", currency=Currency.USD, min_amount=1))
        s.add(PaymentMethod(code="sham_syp", name_ar="شام كاش ل.س", name_en="ShamCash SYP", currency=Currency.SYP, min_amount=10000))
        await s.commit()
    yield maker
    await engine.dispose()


async def _deposit(maker, method_id=1, amount=10, ref="TX1"):
    async with maker() as s:
        return await deposits.create_deposit(s, user_id=USER, method_id=method_id, amount=amount, txn_ref=ref, proof_file_id=None)


async def _balance(maker):
    async with maker() as s:
        return await wallet.get_balance(s, USER)


async def test_approve_credits_exactly_once(sm):
    dep = await _deposit(sm, amount=10)
    async with sm() as s:
        await deposits.approve_deposit(s, dep.id, ADMIN, RATE)
    assert await _balance(sm) == 1000
    async with sm() as s:
        with pytest.raises(AlreadyDecided):
            await deposits.approve_deposit(s, dep.id, ADMIN, RATE)
    assert await _balance(sm) == 1000


async def test_rejected_deposit_cannot_be_approved(sm):
    dep = await _deposit(sm)
    async with sm() as s:
        await deposits.reject_deposit(s, dep.id, ADMIN)
    async with sm() as s:
        with pytest.raises(AlreadyDecided):
            await deposits.approve_deposit(s, dep.id, ADMIN, RATE)
    assert await _balance(sm) == 0


async def test_reused_transaction_ref_is_blocked(sm):
    await _deposit(sm, ref="abc 123")
    with pytest.raises(DuplicateTransaction):
        await _deposit(sm, ref="  ABC   123 ")


async def test_syp_deposit_converts_at_rate(sm):
    dep = await _deposit(sm, method_id=2, amount=130000, ref="SYP1")
    async with sm() as s:
        d = await deposits.approve_deposit(s, dep.id, ADMIN, RATE)
    assert d.credited_cents == 1000
    assert await _balance(sm) == 1000


async def test_below_minimum_rejected(sm):
    with pytest.raises(BelowMinimum):
        await _deposit(sm, method_id=2, amount=500, ref="SMALL")


async def test_custom_credit_amount(sm):
    dep = await _deposit(sm, amount=10)
    async with sm() as s:
        await deposits.approve_deposit(s, dep.id, ADMIN, RATE, credited_cents=850)
    assert await _balance(sm) == 850


async def test_purchase_debits_and_refund_restores_once(sm):
    dep = await _deposit(sm, amount=5)
    async with sm() as s:
        await deposits.approve_deposit(s, dep.id, ADMIN, RATE)
    async with sm() as s:
        order = await orders.create_order(s, user_id=USER, package_id=2, player_ref="5123456789", lang="en")
    assert order.status == Status.PENDING
    assert order.game_name == "PUBG Mobile"
    assert await _balance(sm) == 500 - 499

    async with sm() as s:
        await orders.reject_order(s, order.id, ADMIN, "wrong id")
    assert await _balance(sm) == 500
    async with sm() as s:
        with pytest.raises(AlreadyDecided):
            await orders.reject_order(s, order.id, ADMIN)
    assert await _balance(sm) == 500


async def test_insufficient_balance_creates_nothing(sm):
    with pytest.raises(InsufficientBalance):
        async with sm() as s:
            await orders.create_order(s, user_id=USER, package_id=1, player_ref="1", lang="ar")
    async with sm() as s:
        assert await orders.list_for_user(s, USER) == []
    assert await _balance(sm) == 0


async def test_completed_order_cannot_be_refunded(sm):
    dep = await _deposit(sm, amount=1)
    async with sm() as s:
        await deposits.approve_deposit(s, dep.id, ADMIN, RATE)
    async with sm() as s:
        order = await orders.create_order(s, user_id=USER, package_id=1, player_ref="1", lang="ar")
    async with sm() as s:
        await orders.complete_order(s, order.id, ADMIN)
    async with sm() as s:
        with pytest.raises(AlreadyDecided):
            await orders.reject_order(s, order.id, ADMIN)
    assert await _balance(sm) == 1


async def test_admin_adjust_cannot_go_negative(sm):
    async with sm() as s:
        assert await wallet.admin_adjust(s, USER, 300, ADMIN, "bonus") == 300
    async with sm() as s:
        with pytest.raises(InsufficientBalance):
            await wallet.admin_adjust(s, USER, -500, ADMIN, "fix")
    assert await _balance(sm) == 300


def test_money_parsing():
    assert parse_usd_to_cents("12.5") == 1250
    assert parse_usd_to_cents("$3") == 300
    assert parse_usd_to_cents("0") is None
    assert parse_usd_to_cents("1.234") is None
    assert parse_usd_to_cents("abc") is None
    assert syp_to_usd_cents(13000, 13000) == 100
