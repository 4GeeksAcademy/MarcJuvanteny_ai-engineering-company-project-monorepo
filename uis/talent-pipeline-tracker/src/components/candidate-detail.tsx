"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { StageBadge, StatusBadge } from "@/components/badges";
import { CandidateForm } from "@/components/candidate-form";
import { ErrorState, InlineError, LoadingState, SuccessMessage } from "@/components/feedback";
import { NotesPanel } from "@/components/notes-panel";
import { StatusStageEditor } from "@/components/status-stage-editor";
import { ApiError, deleteCandidate, errorMessage, getCandidate, listNotes, updateCandidate } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/labels";
import type { Candidate, CandidateInput, Note } from "@/types/candidate";

type Loaded<T> = { key: string; data?: T; error?: string; notFound?: boolean };

export function CandidateDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [candidateAttempt, setCandidateAttempt] = useState(0);
  const [notesAttempt, setNotesAttempt] = useState(0);
  const [candidate, setCandidate] = useState<Loaded<Candidate> | null>(null);
  const [notes, setNotes] = useState<Loaded<Note[]> | null>(null);
  const [editing, setEditing] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const candidateKey = `${id}#${candidateAttempt}`;
  const notesKey = `${id}#${notesAttempt}`;

  useEffect(() => {
    const controller = new AbortController();
    getCandidate(id, controller.signal)
      .then((data) => setCandidate({ key: candidateKey, data }))
      .catch((error) => {
        if (controller.signal.aborted) return;
        setCandidate({
          key: candidateKey,
          error: errorMessage(error),
          notFound: error instanceof ApiError && error.status === 404,
        });
      });
    return () => controller.abort();
  }, [id, candidateKey]);

  // Las notas se piden aparte: solo se muestran aquí, nunca en el listado.
  useEffect(() => {
    const controller = new AbortController();
    listNotes(id, controller.signal)
      .then((data) => setNotes({ key: notesKey, data: data.data }))
      .catch((error) => {
        if (!controller.signal.aborted) setNotes({ key: notesKey, error: errorMessage(error) });
      });
    return () => controller.abort();
  }, [id, notesKey]);

  function flashSuccess(message: string) {
    setSuccess(message);
    setTimeout(() => setSuccess(null), 3000);
  }

  function replaceCandidate(data: Candidate) {
    setCandidate({ key: candidateKey, data });
  }

  async function handleEdit(input: CandidateInput) {
    const updated = await updateCandidate(id, input);
    replaceCandidate(updated);
    setEditing(false);
    flashSuccess("Datos del candidato actualizados.");
  }

  async function handleDelete() {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteCandidate(id);
      router.replace("/");
    } catch (error) {
      setDeleteError(errorMessage(error));
      setDeleting(false);
    }
  }

  if (candidate?.key !== candidateKey) return <LoadingState label="Cargando candidato..." />;

  if (candidate.error || !candidate.data) {
    return (
      <div className="grid grid-cols-1 gap-4">
        <BackLink />
        <ErrorState
          message={candidate.notFound ? "Este candidato no existe o ha sido eliminado." : candidate.error ?? "Error desconocido."}
          onRetry={candidate.notFound ? undefined : () => setCandidateAttempt((value) => value + 1)}
        />
      </div>
    );
  }

  const data = candidate.data;
  const notesLoaded = notes?.key === notesKey;

  return (
    <div className="grid grid-cols-1 gap-5">
      <BackLink />

      <section className="grid gap-4 rounded-lg border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">{data.full_name}</h1>
            <p className="text-sm text-slate-600">{data.position}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <StatusBadge status={data.status} />
              <StageBadge stage={data.stage} />
            </div>
          </div>
          {!editing ? (
            <button type="button" onClick={() => setEditing(true)} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
              Editar datos
            </button>
          ) : null}
        </div>

        <SuccessMessage message={success} />

        {editing ? (
          <CandidateForm initial={data} submitLabel="Guardar datos" onSubmit={handleEdit} onCancel={() => setEditing(false)} />
        ) : (
          <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
            <Field label="Email">
              <a href={`mailto:${data.email}`} className="text-indigo-700 hover:underline">{data.email}</a>
            </Field>
            <Field label="Teléfono">{data.phone}</Field>
            <Field label="Años de experiencia">{data.experience_years}</Field>
            <Field label="Fecha de postulación">{formatDate(data.applied_at)}</Field>
            <Field label="LinkedIn"><ExternalLink href={data.linkedin_url} label="Ver perfil" /></Field>
            <Field label="CV"><ExternalLink href={data.cv_url} label="Abrir CV" /></Field>
            <Field label="Última actualización">{formatDateTime(data.updated_at)}</Field>
          </dl>
        )}
      </section>

      <StatusStageEditor candidate={data} onUpdated={replaceCandidate} />

      <NotesPanel
        candidateId={id}
        notes={notesLoaded && notes.data ? notes.data : null}
        loadError={notesLoaded ? notes.error ?? null : null}
        onRetry={() => setNotesAttempt((value) => value + 1)}
        onNotesChange={(next) => setNotes({ key: notesKey, data: next })}
      />

      <section className="grid gap-3 rounded-lg border border-red-200 bg-white p-5">
        <h2 className="text-base font-semibold text-red-800">Eliminar candidato</h2>
        <p className="text-sm text-slate-600">Se borrará el candidato y todas sus notas. Esta acción no se puede deshacer.</p>
        <InlineError message={deleteError} />
        <div className="flex justify-end gap-2">
          {confirmDelete ? (
            <>
              <button type="button" disabled={deleting} onClick={() => setConfirmDelete(false)} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">
                Cancelar
              </button>
              <button type="button" disabled={deleting} onClick={handleDelete} className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60">
                {deleting ? "Eliminando..." : "Sí, eliminar"}
              </button>
            </>
          ) : (
            <button type="button" onClick={() => setConfirmDelete(true)} className="rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50">
              Eliminar candidato
            </button>
          )}
        </div>
      </section>
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/" className="text-sm font-medium text-indigo-700 hover:underline">
      ← Volver al listado
    </Link>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-slate-800">{children}</dd>
    </div>
  );
}

function ExternalLink({ href, label }: { href: string | null; label: string }) {
  // Solo se enlazan URLs http(s): evita `javascript:` u otros esquemas en datos de la API.
  if (!href || !/^https?:\/\//i.test(href)) return <span className="text-slate-400">No indicado</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-indigo-700 hover:underline">
      {label}
    </a>
  );
}
