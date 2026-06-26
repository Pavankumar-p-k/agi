/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — MCP Tools API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';

export interface McpTool {
  id: string;
  name: string;
  description: string;
  category: string;
  available: boolean;
}

export const mcp = {
  tools: () =>
    request<{ tools: McpTool[]; total: number }>('/mcp/tools'),
};
