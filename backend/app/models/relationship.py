import enum
from datetime import datetime
from sqlalchemy import Integer, String, DateTime, ForeignKey, UniqueConstraint, Enum
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class RelationType(str, enum.Enum):
    parent = "parent"          # directed: from = parent, to = child
    grandparent = "grandparent"  # directed: from = grandparent, to = grandchild
    partner = "partner"        # symmetric (spouse/partner)
    sibling = "sibling"        # symmetric
    relative = "relative"      # symmetric (other family)
    friend = "friend"          # symmetric
    colleague = "colleague"    # symmetric
    other = "other"            # symmetric


# Which types are directional (hierarchical) vs symmetric — used by the graph.
DIRECTED = {RelationType.parent, RelationType.grandparent}

# Category for colouring/grouping in the UI.
CATEGORY = {
    RelationType.parent: "family", RelationType.grandparent: "family",
    RelationType.partner: "family", RelationType.sibling: "family",
    RelationType.relative: "family", RelationType.friend: "social",
    RelationType.colleague: "social", RelationType.other: "other",
}


class PersonRelationship(Base):
    __tablename__ = "person_relationships"
    __table_args__ = (UniqueConstraint("from_person_id", "to_person_id", "rel_type", name="uq_relationship"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_person_id: Mapped[int] = mapped_column(Integer, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True)
    to_person_id: Mapped[int] = mapped_column(Integer, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True)
    rel_type: Mapped[RelationType] = mapped_column(Enum(RelationType), nullable=False)
    note: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
