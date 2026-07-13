from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ItemCategory(str, Enum):
    CARD = "CARD"
    WALLET = "WALLET"
    EARPHONE = "EARPHONE"
    BAG = "BAG"
    KEY = "KEY"
    ELECTRONICS = "ELECTRONICS"
    CLOTHING = "CLOTHING"
    UMBRELLA = "UMBRELLA"
    STATIONERY = "STATIONERY"
    ETC = "ETC"


ITEM_CATEGORY_LABELS = {
    ItemCategory.CARD: "카드/학생증",
    ItemCategory.WALLET: "지갑",
    ItemCategory.EARPHONE: "이어폰/이어폰 케이스",
    ItemCategory.BAG: "가방",
    ItemCategory.KEY: "열쇠/키링",
    ItemCategory.ELECTRONICS: "전자기기",
    ItemCategory.CLOTHING: "의류",
    ItemCategory.UMBRELLA: "우산",
    ItemCategory.STATIONERY: "문구류",
    ItemCategory.ETC: "기타",
}

ITEM_CATEGORY_TYPE = db.Enum(
    ItemCategory,
    name="item_category",
    native_enum=False,
    create_constraint=False,
    validate_strings=True,
    values_callable=lambda enum: [item.value for item in enum],
)
ITEM_CATEGORY_CHECK = "category IN ({})".format(
    ", ".join(f"'{category.value}'" for category in ItemCategory)
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow, nullable=False)


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(db.String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(db.String(255))
    nickname: Mapped[str] = mapped_column(db.String(20))
    site_code: Mapped[str] = mapped_column(db.String(50), index=True)
    profile_image_url: Mapped[str | None] = mapped_column(db.String(500))
    platform: Mapped[str | None] = mapped_column(db.String(20))
    push_token: Mapped[str | None] = mapped_column(db.String(500))
    is_active: Mapped[bool] = mapped_column(default=True)

    lost_posts: Mapped[list[LostPost]] = relationship(
        back_populates="author", cascade="all, delete-orphan"
    )
    found_posts: Mapped[list[FoundPost]] = relationship(
        back_populates="author", cascade="all, delete-orphan"
    )
    chat_memberships: Mapped[list[ChatRoomMember]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    chat_messages: Mapped[list[ChatMessage]] = relationship(back_populates="sender")

    def public_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "nickname": self.nickname,
            "siteCode": self.site_code,
            "profileImageUrl": self.profile_image_url,
            "platform": self.platform,
            "isActive": self.is_active,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }


class LostPost(TimestampMixin, db.Model):
    __tablename__ = "lost_posts"
    __table_args__ = (
        db.CheckConstraint(ITEM_CATEGORY_CHECK, name="ck_lost_posts_category_enum"),
        Index(
            "ix_lost_post_match_candidates",
            "site_code",
            "status",
            "category",
            "lost_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), index=True)
    site_code: Mapped[str] = mapped_column(db.String(50), index=True)
    title: Mapped[str] = mapped_column(db.String(100))
    category: Mapped[ItemCategory] = mapped_column(ITEM_CATEGORY_TYPE, index=True)
    color: Mapped[str] = mapped_column(db.String(30), index=True)
    location: Mapped[str] = mapped_column(db.String(100), index=True)
    lost_at: Mapped[datetime] = mapped_column(index=True)
    features: Mapped[str] = mapped_column(db.Text)
    private_feature: Mapped[str | None] = mapped_column(db.Text)
    description: Mapped[str | None] = mapped_column(db.Text)
    image_url: Mapped[str | None] = mapped_column(db.String(500))
    contact_method: Mapped[str] = mapped_column(db.String(20), default="NOTIFICATION")
    status: Mapped[str] = mapped_column(db.String(20), default="OPEN", index=True)

    author: Mapped[User] = relationship(back_populates="lost_posts")
    matches: Mapped[list[Match]] = relationship(
        back_populates="lost_post", cascade="all, delete-orphan"
    )

    def to_dict(self, include_private: bool = False) -> dict:
        data = {
            "id": self.id,
            "userId": self.user_id,
            "siteCode": self.site_code,
            "title": self.title,
            "category": self.category.value,
            "color": self.color,
            "location": self.location,
            "lostAt": self.lost_at.isoformat(),
            "features": self.features,
            "description": self.description,
            "imageUrl": self.image_url,
            "contactMethod": self.contact_method,
            "status": self.status,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }
        if include_private:
            data["privateFeature"] = self.private_feature
        return data


class FoundPost(TimestampMixin, db.Model):
    __tablename__ = "found_posts"
    __table_args__ = (
        db.CheckConstraint(ITEM_CATEGORY_CHECK, name="ck_found_posts_category_enum"),
        Index(
            "ix_found_post_match_candidates",
            "site_code",
            "status",
            "category",
            "found_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), index=True)
    site_code: Mapped[str] = mapped_column(db.String(50), index=True)
    title: Mapped[str] = mapped_column(db.String(100))
    category: Mapped[ItemCategory] = mapped_column(ITEM_CATEGORY_TYPE, index=True)
    color: Mapped[str] = mapped_column(db.String(30), index=True)
    location: Mapped[str] = mapped_column(db.String(100), index=True)
    found_at: Mapped[datetime] = mapped_column(index=True)
    storage_location: Mapped[str] = mapped_column(db.String(100))
    features: Mapped[str] = mapped_column(db.Text)
    private_feature: Mapped[str | None] = mapped_column(db.Text)
    verification_question: Mapped[str | None] = mapped_column(db.String(255))
    description: Mapped[str | None] = mapped_column(db.Text)
    image_url: Mapped[str | None] = mapped_column(db.String(500))
    status: Mapped[str] = mapped_column(db.String(20), default="STORED", index=True)

    author: Mapped[User] = relationship(back_populates="found_posts")
    matches: Mapped[list[Match]] = relationship(
        back_populates="found_post", cascade="all, delete-orphan"
    )

    def to_dict(self, include_private: bool = False) -> dict:
        data = {
            "id": self.id,
            "userId": self.user_id,
            "siteCode": self.site_code,
            "title": self.title,
            "category": self.category.value,
            "color": self.color,
            "location": self.location,
            "foundAt": self.found_at.isoformat(),
            "features": self.features,
            "description": self.description,
            "imageUrl": self.image_url,
            "status": self.status,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }
        if include_private:
            data["storageLocation"] = self.storage_location
            data["privateFeature"] = self.private_feature
            data["verificationQuestion"] = self.verification_question
        return data


class Match(TimestampMixin, db.Model):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("lost_post_id", "found_post_id", name="uq_match_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lost_post_id: Mapped[int] = mapped_column(db.ForeignKey("lost_posts.id"), index=True)
    found_post_id: Mapped[int] = mapped_column(db.ForeignKey("found_posts.id"), index=True)
    score: Mapped[Decimal] = mapped_column(db.Numeric(5, 2), index=True)
    category_score: Mapped[Decimal] = mapped_column(db.Numeric(5, 2))
    color_score: Mapped[Decimal] = mapped_column(db.Numeric(5, 2))
    location_score: Mapped[Decimal] = mapped_column(db.Numeric(5, 2))
    time_score: Mapped[Decimal] = mapped_column(db.Numeric(5, 2))
    feature_score: Mapped[Decimal] = mapped_column(db.Numeric(5, 2))
    reasons: Mapped[list] = mapped_column(db.JSON, default=list)
    model_version: Mapped[str] = mapped_column(db.String(50))
    status: Mapped[str] = mapped_column(db.String(30), default="CANDIDATE", index=True)
    claim_answer: Mapped[str | None] = mapped_column(db.Text)
    claim_message: Mapped[str | None] = mapped_column(db.String(500))
    claimed_at: Mapped[datetime | None]
    confirmed_by: Mapped[int | None] = mapped_column(db.ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None]
    rejection_reason: Mapped[str | None] = mapped_column(db.String(500))
    handed_over_at: Mapped[datetime | None]

    lost_post: Mapped[LostPost] = relationship(back_populates="matches")
    found_post: Mapped[FoundPost] = relationship(back_populates="matches")
    confirmer: Mapped[User | None] = relationship(foreign_keys=[confirmed_by])
    chat_room: Mapped[ChatRoom | None] = relationship(
        back_populates="match",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )

    def to_dict(self, include_posts: bool = True, include_sensitive: bool = False) -> dict:
        score = float(self.score)
        data = {
            "id": self.id,
            "lostPostId": self.lost_post_id,
            "foundPostId": self.found_post_id,
            "score": score,
            "grade": ("VERY_HIGH" if score >= 85 else "HIGH" if score >= 70 else "MEDIUM"),
            "scoreDetails": {
                "category": float(self.category_score),
                "color": float(self.color_score),
                "location": float(self.location_score),
                "time": float(self.time_score),
                "feature": float(self.feature_score),
            },
            "reasons": self.reasons,
            "modelVersion": self.model_version,
            "status": self.status,
            "chatRoomId": self.chat_room.id if self.chat_room else None,
            "claimedAt": self.claimed_at.isoformat() if self.claimed_at else None,
            "confirmedBy": self.confirmed_by,
            "confirmedAt": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "rejectionReason": self.rejection_reason,
            "handedOverAt": (self.handed_over_at.isoformat() if self.handed_over_at else None),
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }
        if include_posts:
            data["lostPost"] = self.lost_post.to_dict()
            data["foundPost"] = self.found_post.to_dict()
        if include_sensitive:
            data["claimAnswer"] = self.claim_answer
            data["claimMessage"] = self.claim_message
        return data


class ChatRoom(TimestampMixin, db.Model):
    __tablename__ = "chat_rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(
        db.ForeignKey("matches.id", ondelete="CASCADE"), unique=True, index=True
    )

    match: Mapped[Match] = relationship(back_populates="chat_room")
    members: Mapped[list[ChatRoomMember]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )
    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )


class ChatRoomMember(TimestampMixin, db.Model):
    __tablename__ = "chat_room_members"
    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_chat_room_member"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(
        db.ForeignKey("chat_rooms.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), index=True)
    last_read_message_id: Mapped[int | None] = mapped_column(index=True)
    last_read_at: Mapped[datetime | None] = mapped_column(index=True)

    room: Mapped[ChatRoom] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="chat_memberships")


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint(
            "room_id",
            "sender_id",
            "client_message_id",
            name="uq_chat_message_client_id",
        ),
        Index("ix_chat_messages_room_id_id", "room_id", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(
        db.ForeignKey("chat_rooms.id", ondelete="CASCADE"), index=True
    )
    sender_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(db.String(1000))
    client_message_id: Mapped[str | None] = mapped_column(db.String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False, index=True)

    room: Mapped[ChatRoom] = relationship(back_populates="messages")
    sender: Mapped[User] = relationship(back_populates="chat_messages")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "roomId": self.room_id,
            "sender": {
                "id": self.sender.id,
                "nickname": self.sender.nickname,
                "profileImageUrl": self.sender.profile_image_url,
            },
            "content": self.content,
            "clientMessageId": self.client_message_id,
            "createdAt": self.created_at.isoformat(),
        }
