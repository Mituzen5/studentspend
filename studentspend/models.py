from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False, index=True)
    name = db.Column(db.String(60), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    default_allowance = db.Column(db.Float, nullable=False, default=0)
    session_version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    months = db.relationship("Month", backref="user", cascade="all, delete-orphan", lazy="dynamic")
    transactions = db.relationship("Transaction", backref="user", cascade="all, delete-orphan", lazy="dynamic")
    goals = db.relationship("Goal", backref="user", cascade="all, delete-orphan", lazy="dynamic")
    challenges = db.relationship("ChallengeDay", backref="user", cascade="all, delete-orphan", lazy="dynamic")
    limits = db.relationship("CategoryLimit", backref="user", cascade="all, delete-orphan", lazy="dynamic")


class Month(db.Model):
    """One budget cycle (YYYY-MM). Carry-forward is derived from the previous cycle."""
    __tablename__ = "months"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    month = db.Column(db.String(7), nullable=False)
    allowance = db.Column(db.Float, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    __table_args__ = (db.UniqueConstraint("user_id", "month", name="uq_user_month"),)


class Transaction(db.Model):
    __tablename__ = "transactions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False)  # expense | saving
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(40), nullable=False)
    note = db.Column(db.String(120), nullable=False, default="")
    date = db.Column(db.String(10), nullable=False, index=True)  # YYYY-MM-DD
    month = db.Column(db.String(7), nullable=False, index=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("goals.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)


class Goal(db.Model):
    __tablename__ = "goals"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(60), nullable=False)
    emoji = db.Column(db.String(8), nullable=False, default="🎯")
    target = db.Column(db.Float, nullable=False)
    deadline = db.Column(db.String(10), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)


class ChallengeDay(db.Model):
    __tablename__ = "challenge_days"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date = db.Column(db.String(10), nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "date", name="uq_user_challenge"),)


class CategoryLimit(db.Model):
    __tablename__ = "category_limits"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category = db.Column(db.String(40), nullable=False)
    limit = db.Column(db.Float, nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "category", name="uq_user_category"),)
