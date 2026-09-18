"""Persistent lexical retrieval over project source chunks."""

from __future__ import annotations

from dataclasses import dataclass

from deeper_dive.storage.database import Database


@dataclass(frozen=True, slots=True)
class LexicalHit:
    """One stable, scored lexical retrieval result."""

    chunk_id: str
    source_id: str
    score: float
    text: str
    location: str | None


class LexicalIndex:
    """SQLite FTS5 index kept in sync from authoritative source chunks."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()
        with self.database.transaction() as db:
            db.execute(
                """CREATE VIRTUAL TABLE IF NOT EXISTS lexical_chunks USING fts5(
                    chunk_id UNINDEXED, source_id UNINDEXED, text,
                    content='source_chunks', content_rowid='rowid'
                )"""
            )
            db.execute(
                """CREATE TRIGGER IF NOT EXISTS lexical_chunks_ai AFTER INSERT ON source_chunks BEGIN
                    INSERT INTO lexical_chunks(rowid,chunk_id,source_id,text)
                    VALUES (new.rowid,new.id,new.source_id,new.text);
                END"""
            )
            db.execute(
                """CREATE TRIGGER IF NOT EXISTS lexical_chunks_ad AFTER DELETE ON source_chunks BEGIN
                    INSERT INTO lexical_chunks(lexical_chunks,rowid,chunk_id,source_id,text)
                    VALUES ('delete',old.rowid,old.id,old.source_id,old.text);
                END"""
            )
            db.execute(
                """CREATE TRIGGER IF NOT EXISTS lexical_chunks_au AFTER UPDATE ON source_chunks BEGIN
                    INSERT INTO lexical_chunks(lexical_chunks,rowid,chunk_id,source_id,text)
                    VALUES ('delete',old.rowid,old.id,old.source_id,old.text);
                    INSERT INTO lexical_chunks(rowid,chunk_id,source_id,text)
                    VALUES (new.rowid,new.id,new.source_id,new.text);
                END"""
            )
            db.execute("INSERT INTO lexical_chunks(lexical_chunks) VALUES ('rebuild')")

    def search(self, project_id: str, query: str, *, limit: int = 10) -> list[LexicalHit]:
        """Return included project chunks ordered by BM25 relevance and stable chunk ID."""

        if limit <= 0 or not query.strip():
            return []
        with self.database.connection() as db:
            rows = db.execute(
                """SELECT lc.chunk_id,lc.source_id,bm25(lexical_chunks) AS rank,
                          sc.text,sc.location
                   FROM lexical_chunks lc
                   JOIN source_chunks sc ON sc.id=lc.chunk_id
                   JOIN sources s ON s.id=lc.source_id
                   WHERE lexical_chunks MATCH ? AND s.project_id=? AND s.included=1
                   ORDER BY rank ASC, lc.chunk_id ASC LIMIT ?""",
                (query, project_id, limit),
            ).fetchall()
        return [
            LexicalHit(
                chunk_id=str(row["chunk_id"]),
                source_id=str(row["source_id"]),
                score=-float(row["rank"]),
                text=str(row["text"]),
                location=None if row["location"] is None else str(row["location"]),
            )
            for row in rows
        ]
