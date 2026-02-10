"""FastAPI backend for the Simple Notes App.

Provides a REST API to create, read, update, and delete notes stored in SQLite.

Environment variables:
- SQLITE_DB: Absolute path to the SQLite database file (provided by notes_database container).
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Path, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

openapi_tags = [
    {"name": "Health", "description": "Health and service status endpoints."},
    {"name": "Notes", "description": "CRUD operations for notes."},
]


def _get_db_path() -> str:
    """Get SQLite DB path from environment, with a safe fallback for local dev."""
    # NOTE: In the target environment, SQLITE_DB is expected to be provided.
    env_path = os.getenv("SQLITE_DB")
    if env_path:
        return env_path
    # Fallback (local dev): point to the known workspace DB if env var is absent.
    return "/home/kavia/workspace/code-generation/simple-notes-app-216444-216458/notes_database/myapp.db"


def _get_connection() -> sqlite3.Connection:
    """Create a new SQLite connection with row dict support."""
    conn = sqlite3.connect(_get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_db() -> None:
    """Ensure required schema exists (safe to call on startup)."""
    conn = _get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON notes(updated_at)")
        conn.commit()
    finally:
        conn.close()


class NoteBase(BaseModel):
    """Shared fields for notes."""

    title: str = Field(..., min_length=1, max_length=200, description="Note title.")
    content: str = Field(..., min_length=1, description="Note content/body.")


class NoteCreate(NoteBase):
    """Request model for creating a note."""


class NoteUpdate(BaseModel):
    """Request model for updating a note (partial updates allowed)."""

    title: Optional[str] = Field(None, min_length=1, max_length=200, description="Updated note title.")
    content: Optional[str] = Field(None, min_length=1, description="Updated note content/body.")


class NoteOut(NoteBase):
    """Response model for notes."""

    id: int = Field(..., description="Unique note id.")
    created_at: datetime = Field(..., description="Creation timestamp.")
    updated_at: datetime = Field(..., description="Last update timestamp.")


app = FastAPI(
    title="Simple Notes API",
    description="A simple REST API for a notes app backed by SQLite.",
    version="0.1.0",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    """Initialize required database schema on startup."""
    _init_db()


@app.get("/", tags=["Health"], summary="Health check", description="Basic health check endpoint.")
def health_check():
    """Return service health.

    Returns:
        JSON payload indicating service health.
    """
    return {"message": "Healthy"}


# PUBLIC_INTERFACE
@app.get(
    "/notes",
    tags=["Notes"],
    response_model=List[NoteOut],
    summary="List notes",
    description="Return notes ordered by most recently updated first.",
    operation_id="list_notes",
)
def list_notes(
    limit: int = Query(200, ge=1, le=500, description="Maximum number of notes to return."),
    offset: int = Query(0, ge=0, description="Number of notes to skip."),
):
    """List notes.

    Args:
        limit: max notes to return.
        offset: notes to skip for pagination.

    Returns:
        A list of notes.
    """
    conn = _get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, title, content, created_at, updated_at
            FROM notes
            ORDER BY datetime(updated_at) DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [
            NoteOut(
                id=row["id"],
                title=row["title"],
                content=row["content"],
                created_at=datetime.fromisoformat(str(row["created_at"]).replace("Z", "")),
                updated_at=datetime.fromisoformat(str(row["updated_at"]).replace("Z", "")),
            )
            for row in rows
        ]
    finally:
        conn.close()


# PUBLIC_INTERFACE
@app.get(
    "/notes/{note_id}",
    tags=["Notes"],
    response_model=NoteOut,
    summary="Get note",
    description="Fetch a single note by id.",
    operation_id="get_note",
)
def get_note(note_id: int = Path(..., ge=1, description="Note id to fetch.")):
    """Get a note by id.

    Args:
        note_id: The note id.

    Returns:
        The note.
    """
    conn = _get_connection()
    try:
        row = conn.execute(
            """
            SELECT id, title, content, created_at, updated_at
            FROM notes
            WHERE id = ?
            """,
            (note_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Note not found")
        return NoteOut(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            created_at=datetime.fromisoformat(str(row["created_at"]).replace("Z", "")),
            updated_at=datetime.fromisoformat(str(row["updated_at"]).replace("Z", "")),
        )
    finally:
        conn.close()


# PUBLIC_INTERFACE
@app.post(
    "/notes",
    tags=["Notes"],
    response_model=NoteOut,
    status_code=201,
    summary="Create note",
    description="Create a new note with title and content.",
    operation_id="create_note",
)
def create_note(payload: NoteCreate):
    """Create a note.

    Args:
        payload: Note title and content.

    Returns:
        The newly created note.
    """
    now = datetime.utcnow().isoformat(timespec="seconds")
    conn = _get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO notes (title, content, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (payload.title.strip(), payload.content, now, now),
        )
        conn.commit()
        note_id = int(cur.lastrowid)
        row = conn.execute(
            """
            SELECT id, title, content, created_at, updated_at
            FROM notes
            WHERE id = ?
            """,
            (note_id,),
        ).fetchone()
        return NoteOut(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            created_at=datetime.fromisoformat(str(row["created_at"]).replace("Z", "")),
            updated_at=datetime.fromisoformat(str(row["updated_at"]).replace("Z", "")),
        )
    finally:
        conn.close()


# PUBLIC_INTERFACE
@app.put(
    "/notes/{note_id}",
    tags=["Notes"],
    response_model=NoteOut,
    summary="Update note",
    description="Update an existing note. Fields omitted are left unchanged.",
    operation_id="update_note",
)
def update_note(
    payload: NoteUpdate,
    note_id: int = Path(..., ge=1, description="Note id to update."),
):
    """Update an existing note.

    Args:
        payload: Partial note fields (title/content).
        note_id: The note id.

    Returns:
        The updated note.
    """
    if payload.title is None and payload.content is None:
        raise HTTPException(status_code=400, detail="At least one field (title/content) must be provided")

    conn = _get_connection()
    try:
        existing = conn.execute("SELECT id, title, content, created_at, updated_at FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Note not found")

        new_title = payload.title.strip() if payload.title is not None else existing["title"]
        new_content = payload.content if payload.content is not None else existing["content"]
        now = datetime.utcnow().isoformat(timespec="seconds")

        conn.execute(
            """
            UPDATE notes
            SET title = ?, content = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_title, new_content, now, note_id),
        )
        conn.commit()

        row = conn.execute(
            "SELECT id, title, content, created_at, updated_at FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()

        return NoteOut(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            created_at=datetime.fromisoformat(str(row["created_at"]).replace("Z", "")),
            updated_at=datetime.fromisoformat(str(row["updated_at"]).replace("Z", "")),
        )
    finally:
        conn.close()


# PUBLIC_INTERFACE
@app.delete(
    "/notes/{note_id}",
    tags=["Notes"],
    status_code=204,
    summary="Delete note",
    description="Delete a note by id.",
    operation_id="delete_note",
)
def delete_note(note_id: int = Path(..., ge=1, description="Note id to delete.")):
    """Delete a note.

    Args:
        note_id: The note id.

    Returns:
        An empty response (204) on success.
    """
    conn = _get_connection()
    try:
        cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Note not found")
        return Response(status_code=204)
    finally:
        conn.close()
