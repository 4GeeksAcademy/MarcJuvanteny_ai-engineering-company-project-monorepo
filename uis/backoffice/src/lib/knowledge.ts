export const KNOWLEDGE_API_URL = process.env.NEXT_PUBLIC_KNOWLEDGE_API_URL || "http://localhost:8020";

// Hito 10 Parte 2: el panel de chat ya no usa POST /knowledge/query
// (petición/respuesta única) -- habla con el First-line CX agent por
// WebSocket, ver `use-cx-chat.ts`. El endpoint sigue existiendo en
// services/knowledge-api para otros consumidores.
