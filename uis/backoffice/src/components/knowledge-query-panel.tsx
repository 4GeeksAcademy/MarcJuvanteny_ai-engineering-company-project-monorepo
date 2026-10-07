"use client";

import { FormEvent, useState } from "react";

import { queryKnowledgeBase } from "@/lib/knowledge";

const EXAMPLE_QUESTIONS = [
  "¿Cuál es la ventana de devolución estándar?",
  "¿Qué transportista cubre mejor Aragón rural?",
  "¿Se puede prometer el SLA estándar durante el Black Friday?",
];

export function KnowledgeQueryPanel() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    // No dejamos la respuesta anterior visible mientras carga la nueva --
    // una respuesta vieja junto a un spinner puede leerse como si ya
    // respondiera la pregunta nueva.
    setAnswer(null);

    try {
      const result = await queryKnowledgeBase(trimmed);
      setAnswer(result);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "No se pudo conectar con la base de conocimiento."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="knowledge-layout">
      <div className="card knowledge-form-card">
        <p className="panel-title">Preguntale a la base de conocimiento</p>
        <form onSubmit={handleSubmit} className="knowledge-form">
          <label className="field-block field-block-wide">
            <span>Pregunta del cliente</span>
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ej: ¿cuál es la ventana de devolución estándar?"
              rows={3}
              disabled={isSubmitting}
            />
          </label>

          <div className="knowledge-examples">
            <span>Ejemplos:</span>
            {EXAMPLE_QUESTIONS.map((example) => (
              <button
                key={example}
                type="button"
                className="knowledge-example-chip"
                onClick={() => setQuestion(example)}
                disabled={isSubmitting}
              >
                {example}
              </button>
            ))}
          </div>

          <button type="submit" className="primary-button" disabled={isSubmitting || !question.trim()}>
            {isSubmitting ? "Consultando…" : "Preguntar"}
          </button>
        </form>
      </div>

      <div className="card knowledge-answer-card" aria-live="polite">
        <p className="panel-title">Respuesta</p>

        {isSubmitting ? <p className="knowledge-status">Buscando en la base de conocimiento…</p> : null}

        {!isSubmitting && error ? <p className="feedback-error">{error}</p> : null}

        {!isSubmitting && !error && answer ? <p className="knowledge-answer">{answer}</p> : null}

        {!isSubmitting && !error && !answer ? (
          <p className="knowledge-status">Escribí una pregunta y presioná &quot;Preguntar&quot; para ver la respuesta acá.</p>
        ) : null}
      </div>
    </div>
  );
}
