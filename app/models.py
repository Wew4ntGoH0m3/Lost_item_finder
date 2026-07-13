from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow, nullable=False)


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(db.String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(db.String(255))
    nickname: Mapped[str] = mapped_column(db.String(20))
    role: Mapped[str] = mapped_column(db.String(20), default="USER", index=True)
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

    def public_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "nickname": self.nickname,
            "role": self.role,
            "siteCode": self.site_code,
            "profileImageUrl": self.profile_image_url,
            "platform": self.platform,
            "isActive": self.is_active,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }


class LostPost(TimestampMixin, db.Model):
    __tablename__ = "lost_posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), index=True)
    site_code: Mapped[str] = mapped_column(db.String(50), index=True)
    title: Mapped[str] = mapped_column(db.String(100))
    category: Mapped[str] = mapped_column(db.String(50), index=True)
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
            "category": self.category,
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
    category: Mapped[str] = mapped_column(db.String(50), index=True)
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
            "category": self.category,
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
