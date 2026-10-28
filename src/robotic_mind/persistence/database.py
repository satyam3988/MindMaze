from sqlalchemy import JSON, Column, Integer, String, create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


class Record(Base):
    """Typed domain aggregates in a small indexed document table."""

    __tablename__ = "records"
    id = Column(String, primary_key=True)
    kind = Column(String, nullable=False, index=True)
    space_id = Column(String, nullable=False, index=True)
    owner_id = Column(String, nullable=False, default="", index=True)
    data = Column(JSON, nullable=False)


class EventRow(Base):
    __tablename__ = "events"
    sequence = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(String, nullable=False, index=True)
    data = Column(JSON, nullable=False)


class Database:
    def __init__(self, url: str):
        self.engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def sqlite_config(connection, _):
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")

        Base.metadata.create_all(self.engine)

    def put(self, kind: str, id: str, space_id: str, data: dict, owner_id: str = ""):
        with Session(self.engine) as session:
            existing = session.get(Record, id)
            if existing and (
                existing.kind != kind
                or existing.space_id != space_id
                or existing.owner_id != owner_id
            ):
                raise ValueError("Record identity conflicts with another owner or entity")
            session.merge(Record(id=id, kind=kind, space_id=space_id, owner_id=owner_id, data=data))
            session.commit()

    def get(self, id: str, kind: str | None = None) -> dict:
        with Session(self.engine) as session:
            row = session.get(Record, id)
            if row is None or (kind and row.kind != kind):
                raise KeyError(f"Unknown {kind or 'record'}: {id}")
            return row.data

    def list(self, kind: str, space_id: str | None = None, owner_id: str | None = None):
        stmt = select(Record).where(Record.kind == kind)
        if space_id is not None:
            stmt = stmt.where(Record.space_id == space_id)
        if owner_id is not None:
            stmt = stmt.where(Record.owner_id == owner_id)
        with Session(self.engine) as session:
            return [row.data for row in session.scalars(stmt)]

    def append_event(self, event_data: dict) -> dict:
        with Session(self.engine) as session:
            row = EventRow(space_id=event_data["space_id"], data=event_data)
            session.add(row)
            session.flush()
            result = {**event_data, "sequence": row.sequence}
            row.data = result
            session.commit()
            return result

    def events(self, space_id: str, after: int = 0, limit: int = 200):
        with Session(self.engine) as session:
            rows = session.scalars(
                select(EventRow)
                .where(EventRow.space_id == space_id, EventRow.sequence > after)
                .order_by(EventRow.sequence.desc())
                .limit(limit)
            ).all()
            return [row.data for row in reversed(rows)]
