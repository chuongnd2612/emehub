// Knowledge — per-project sources and indexed sections.
//
// STUBS. Each function names the endpoint that will replace it.

import { KNOWLEDGE_SECTIONS, KNOWLEDGE_SOURCES } from "./fixtures/knowledge";
import { after, READ_DELAY_MS } from "./timing";
import type { KnowledgeSection, KnowledgeSource } from "./types";

// STUB: GET /api/projects/{projectId}/knowledge/sources
export const getKnowledgeSources = (
  projectId: string,
): Promise<KnowledgeSource[]> =>
  after(
    KNOWLEDGE_SOURCES.filter((k) => k.projectId === projectId),
    READ_DELAY_MS,
  );

// STUB: GET /api/projects/{projectId}/knowledge/sections
export const getKnowledgeSections = (
  _projectId: string,
): Promise<KnowledgeSection[]> => after(KNOWLEDGE_SECTIONS, READ_DELAY_MS);

/** Starts indexing. Immediate — the caller switches to the knowledge tab. */
// STUB: POST /api/projects/{projectId}/knowledge/build
export const buildKnowledge = (_projectId: string): Promise<void> =>
  after(undefined, READ_DELAY_MS);
