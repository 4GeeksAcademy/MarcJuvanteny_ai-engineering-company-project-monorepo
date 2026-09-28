import { extractErrorMessage } from "@/lib/api-errors";

export const KNOWLEDGE_API_URL = process.env.NEXT_PUBLIC_KNOWLEDGE_API_URL || "http://localhost:8020";

export type QueryKnowledgeBaseResponse = {
  answer: string;
};

// Sin authFetch/Bearer token a propósito: POST /knowledge/query
// (services/knowledge-api/) no requiere autenticación (ver
// Pasos/rag-knowledge-base-fase1.md, Fase 3) -- distinto del resto de
// llamadas del backoffice, que sí pasan por useAuth().authFetch.
export async function queryKnowledgeBase(question: string): Promise<string> {
  const response = await fetch(`${KNOWLEDGE_API_URL}/knowledge/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(extractErrorMessage(data, "No se pudo obtener una respuesta de la base de conocimiento."));
  }

  return (data as QueryKnowledgeBaseResponse).answer;
}
