"""Database models for Dogs Bet.

Money rule: a user's balance is never stored as an editable number. It is the SUM of
their ledger entries (USD cents). Every top-up, withdrawal, refund and admin adjustment
is one ledger row, so the books always add up and nothing can be credited twice.
"""

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Status(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class LedgerKind(StrEnum):
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"
    PURCHASE = "purchase"
    REFUND = "refund"
    ADJUST = "adjust"
    GIFT = "gift"
    REFERRAL = "referral"


class Currency(StrEnum):
    USD = "USD"
    SYP = "SYP"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)  # Telegram user id
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str] = mapped_column(String(256), default="")
    lang: Mapped[str | None] = mapped_column(String(2))
    accepted_terms: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    referrer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Linked platform accounts (one user can have multiple if needed)
    platform_accounts: Mapped[list["PlatformAccount"]] = relationship(back_populates="user")


class PlatformAccount(Base):
    """A player account on the real betting platform (created via Agent API or manually)."""
    __tablename__ = "platform_accounts"
    __table_args__ = (UniqueConstraint("username", name="uq_platform_username"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    username: Mapped[str] = mapped_column(String(64))  # platform login
    password: Mapped[str | None] = mapped_column(String(128))  # stored only if we generate it
    platform_player_id: Mapped[str | None] = mapped_column(String(64))  # external ID from Agent API
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="platform_accounts")


class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name_ar: Mapped[str] = mapped_column(String(64))
    name_en: Mapped[str] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(3), default=Currency.USD)
    details_ar: Mapped[str] = mapped_column(Text, default="")
    details_en: Mapped[str] = mapped_column(Text, default="")
    # Optional QR image file_id or static path for ShamCash etc.
    qr_file_id: Mapped[str | None] = mapped_column(String(256))
    min_amount: Mapped[int] = mapped_column(Integer, default=1)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # True = for deposits, False = for withdrawals (or both)
    for_deposit: Mapped[bool] = mapped_column(Boolean, default=True)
    for_withdraw: Mapped[bool] = mapped_column(Boolean, default=False)

    def name(self, lang: str) -> str:
        return self.name_ar if lang == "ar" else self.name_en

    def details(self, lang: str) -> str:
        return self.details_ar if lang == "ar" else self.details_en


class Deposit(Base):
    __tablename__ = "deposits"
    __table_args__ = (
        UniqueConstraint("method_id", "txn_ref", name="uq_deposit_method_txn"),
        CheckConstraint("amount > 0", name="ck_deposit_amount_positive"),
        Index("ix_deposits_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    method_id: Mapped[int] = mapped_column(ForeignKey("payment_methods.id"))
    amount: Mapped[int] = mapped_column(Integer)  # whole units of currency
    currency: Mapped[str] = mapped_column(String(3))
    txn_ref: Mapped[str] = mapped_column(String(128))
    proof_file_id: Mapped[str | None] = mapped_column(String(256))
    credited_cents: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default=Status.PENDING)
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    method: Mapped[PaymentMethod] = relationship()
    user: Mapped[User] = relationship()


class Withdrawal(Base):
    __tablename__ = "withdrawals"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="ck_withdraw_amount_positive"),
        Index("ix_withdrawals_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    method_code: Mapped[str] = mapped_column(String(32))  # shamcash, crypto, etc.
    destination: Mapped[str] = mapped_column(String(256))  # wallet address / account number
    status: Mapped[str] = mapped_column(String(16), default=Status.PENDING)
    admin_note: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class GiftCode(Base):
    __tablename__ = "gift_codes"
    __table_args__ = (UniqueConstraint("code", name="uq_gift_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32))
    amount_cents: Mapped[int] = mapped_column(Integer)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GiftRedemption(Base):
    __tablename__ = "gift_redemptions"
    __table_args__ = (UniqueConstraint("code_id", "user_id", name="uq_gift_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code_id: Mapped[int] = mapped_column(ForeignKey("gift_codes.id"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    amount_cents: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LedgerEntry(Base):
    __tablename__ = "ledger"
    __table_args__ = (
        UniqueConstraint("kind", "ref_id", name="uq_ledger_kind_ref"),
        CheckConstraint("amount_cents <> 0", name="ck_ledger_nonzero"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)  # + credit, - debit
    kind: Mapped[str] = mapped_column(String(16))
    ref_id: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


# Keep Game/Package for possible future "shop" feature, but they are optional now
class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_ar: Mapped[str] = mapped_column(String(128))
    name_en: Mapped[str] = mapped_column(String(128))
    emoji: Mapped[str] = mapped_column(String(8), default="🎮")
    id_label_ar: Mapped[str] = mapped_column(String(64), default="ID اللاعب")
    id_label_en: Mapped[str] = mapped_column(String(64), default="Player ID")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    packages: Mapped[list["Package"]] = relationship(back_populates="game", order_by="Package.sort")

    def name(self, lang: str) -> str:
        return self.name_ar if lang == "ar" else self.name_en

    def id_label(self, lang: str) -> str:
        return self.id_label_ar if lang == "ar" else self.id_label_en


class Package(Base):
    __tablename__ = "packages"
    __table_args__ = (CheckConstraint("price_cents > 0", name="ck_package_price_positive"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(64))
    price_cents: Mapped[int] = mapped_column(Integer)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    game: Mapped[Game] = relationship(back_populates="packages")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("price_cents > 0", name="ck_order_price_positive"),
        Index("ix_orders_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    package_id: Mapped[int | None] = mapped_column(ForeignKey("packages.id", ondelete="SET NULL"))
    game_name: Mapped[str] = mapped_column(String(128))
    package_title: Mapped[str] = mapped_column(String(64))
    price_cents: Mapped[int] = mapped_column(Integer)
    player_ref: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default=Status.PENDING)
    admin_note: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()
