import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    externalDir: true,
  },
  // Proxy opcional para entornos donde el navegador no puede llegar a
  // `localhost:8001` (p. ej. GitHub Codespaces abierto desde el navegador).
  // Con BACKEND_PROXY_TARGET=http://localhost:8001 y
  // NEXT_PUBLIC_INCIDENTS_API_URL=/backend en .env.local, el navegador llama a
  // /backend/* en el mismo origen que la página y Next.js lo reenvía a la API
  // desde el servidor. Sin la variable, no se añade ninguna regla.
  // Igual para la knowledge-api (incluido el WebSocket del chat) con
  // KNOWLEDGE_PROXY_TARGET y NEXT_PUBLIC_KNOWLEDGE_API_URL=/knowledge-backend.
  async rewrites() {
    const rules = [];
    const target = process.env.BACKEND_PROXY_TARGET;
    if (target) rules.push({ source: "/backend/:path*", destination: `${target}/:path*` });
    const knowledgeTarget = process.env.KNOWLEDGE_PROXY_TARGET;
    if (knowledgeTarget) {
      rules.push({ source: "/knowledge-backend/:path*", destination: `${knowledgeTarget}/:path*` });
    }
    return rules;
  },
};

export default nextConfig;
