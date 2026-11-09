"use client";

import { useState, type FormEvent } from "react";

import { ErrorState, InlineError, LoadingState, SuccessMessage } from "@/components/feedback";
import { createNote, deleteNote, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/labels";
import type { Note } from "@/types/candidate";

type NotesPanelProps = {
  candidateId: string;
  notes: Note[] | null;
  loadError: string | null;
  onRetry: () => void;
  onNotesChange: (notes: Note[]) => void;
};

const MAX_NOTE_LENGTH = 2000;

export function NotesPanel({ candidateId, notes, loadError, onRetry, onNotesChange }: NotesPanelProps) {
  const [draft, setDraft] = useState("");
  const [adding, setAdding] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  function flashSuccess(message: string) {
    setSuccess(message);
    setTimeout(() => setSuccess(null), 3000);
  }

  async function handleAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || !notes) return;
    setAdding(true);
    setError(null);
    try {
      const note = await createNote(candidateId, content);
      onNotesChange([...notes, note]);
      setDraft("");
      flashSuccess("Nota añadida.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(noteId: string) {
    if (!notes) return;
    setDeletingId(noteId);
    setError(null);
    try {
      await deleteNote(candidateId, noteId);
      onNotesChange(notes.filter((note) => note.id !== noteId));
      flashSuccess("Nota eliminada.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <section aria-labelledby="notes-heading" className="grid gap-4 rounded-lg border border-slate-200 bg-white p-5">
      <h2 id="notes-heading" className="text-base font-semibold text-slate-900">
        Notas internas {notes ? <span className="font-normal text-slate-500">({notes.length})</span> : null}
      </h2>

      {loadError ? (
        <ErrorState message={loadError} onRetry={onRetry} />
      ) : notes === null ? (
        <LoadingState label="Cargando notas..." />
      ) : (
        <>
          {notes.length === 0 ? (
            <p className="text-sm text-slate-500">Todavía no hay notas para este candidato.</p>
          ) : (
            <ul className="grid gap-3">
              {[...notes]
                .sort((a, b) => a.created_at.localeCompare(b.created_at))
                .map((note) => (
                  <li key={note.id} className="rounded-md border border-slate-200 bg-slate-50 p-3">
                    <p className="whitespace-pre-wrap text-sm text-slate-800">{note.content}</p>
                    <div className="mt-2 flex items-center justify-between gap-2 text-xs text-slate-500">
                      <time dateTime={note.created_at}>{formatDateTime(note.created_at)}</time>
                      <button
                        type="button"
                        onClick={() => handleDelete(note.id)}
                        disabled={deletingId !== null}
                        className="rounded px-2 py-1 font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                      >
                        {deletingId === note.id ? "Eliminando..." : "Eliminar"}
                      </button>
                    </div>
                  </li>
                ))}
            </ul>
          )}

          <form onSubmit={handleAdd} className="grid gap-2">
            <label htmlFor="new-note" className="text-sm font-medium text-slate-700">
              Nueva nota
            </label>
            <textarea
              id="new-note"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              maxLength={MAX_NOTE_LENGTH}
              rows={3}
              placeholder="Impresiones de la entrevista, próximos pasos..."
              className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            />
            <div className="flex justify-end">
              <button type="submit" disabled={adding || !draft.trim()} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50">
                {adding ? "Añadiendo..." : "Añadir nota"}
              </button>
            </div>
          </form>
        </>
      )}

      <InlineError message={error} />
      <SuccessMessage message={success} />
    </section>
  );
}
