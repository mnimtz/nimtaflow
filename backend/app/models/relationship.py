"""Person relationships — family / social / professional graph (Stammbaum).

`rel_type` is stored as a plain string (not a Postgres ENUM) so the type list can
grow freely without enum migrations. RELATION_TYPES is the single source of truth
for labels, category and directionality.
"""
from datetime import datetime
from sqlalchemy import Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


# value: (label, inverse_label | None if symmetric, category, directed)
#   directed=True  → "from" is the senior/source side (parent/uncle/boss);
#                    inverse_label is how it reads from the "to" person's side.
#   directed=False → symmetric (sibling/partner/colleague…), inverse = None.
RELATION_TYPES: dict[str, tuple] = {
    # ── Familie ──────────────────────────────────────────────────────────
    "parent":          ("Elternteil",        "Kind",            "family",       True),
    "father":          ("Vater",             "Kind",            "family",       True),
    "mother":          ("Mutter",            "Kind",            "family",       True),
    "child":           ("Kind",              "Elternteil",      "family",       True),
    "son":             ("Sohn",              "Elternteil",      "family",       True),
    "daughter":        ("Tochter",           "Elternteil",      "family",       True),
    "grandparent":     ("Großelternteil",    "Enkel/in",        "family",       True),
    "grandfather":     ("Großvater",         "Enkel/in",        "family",       True),
    "grandmother":     ("Großmutter",        "Enkel/in",        "family",       True),
    "grandchild":      ("Enkel/in",          "Großelternteil",  "family",       True),
    "uncle":           ("Onkel",             "Nichte/Neffe",    "family",       True),
    "aunt":            ("Tante",             "Nichte/Neffe",    "family",       True),
    "nephew":          ("Neffe",             "Onkel/Tante",     "family",       True),
    "niece":           ("Nichte",            "Onkel/Tante",     "family",       True),
    "sibling":         ("Geschwister",       None,              "family",       False),
    "brother":         ("Bruder",            None,              "family",       False),
    "sister":          ("Schwester",         None,              "family",       False),
    "partner":         ("Partner/in",        None,              "family",       False),
    "husband":         ("Ehemann",           None,              "family",       False),
    "wife":            ("Ehefrau",           None,              "family",       False),
    "ex_partner":      ("Ex-Partner/in",     None,              "family",       False),
    "cousin":          ("Cousin/e",          None,              "family",       False),
    "relative":        ("Verwandt",          None,              "family",       False),
    # ── Sozial ───────────────────────────────────────────────────────────
    "friend":          ("Freund/in",         None,              "social",       False),
    "best_friend":     ("Beste/r Freund/in", None,              "social",       False),
    "acquaintance":    ("Bekannte/r",        None,              "social",       False),
    "neighbor":        ("Nachbar/in",        None,              "social",       False),
    # ── Beruflich ────────────────────────────────────────────────────────
    "colleague":       ("Kollege/in",        None,              "professional", False),
    "boss":            ("Vorgesetzte/r",     "Mitarbeiter/in",  "professional", True),
    "employee":        ("Mitarbeiter/in",    "Vorgesetzte/r",   "professional", True),
    "business_partner":("Geschäftspartner/in", None,            "professional", False),
    # ── Sonstige ─────────────────────────────────────────────────────────
    "other":           ("Sonstige",          None,              "other",        False),
}

DIRECTED = {k for k, v in RELATION_TYPES.items() if v[3]}
CATEGORY = {k: v[2] for k, v in RELATION_TYPES.items()}
LABEL = {k: v[0] for k, v in RELATION_TYPES.items()}
INVERSE_LABEL = {k: (v[1] or v[0]) for k, v in RELATION_TYPES.items()}
# Parent-like links used to derive siblings / grandparents.
PARENT_TYPES = {"parent", "father", "mother"}

CATEGORY_LABELS = {"family": "Familie", "social": "Sozial", "professional": "Beruflich", "other": "Sonstige"}


def meta(rel_type: str) -> tuple:
    return RELATION_TYPES.get(rel_type, ("Verbindung", None, "other", False))


class PersonRelationship(Base):
    __tablename__ = "person_relationships"
    __table_args__ = (UniqueConstraint("from_person_id", "to_person_id", "rel_type", name="uq_relationship"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_person_id: Mapped[int] = mapped_column(Integer, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True)
    to_person_id: Mapped[int] = mapped_column(Integer, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True)
    rel_type: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
