// Projects — the project registry.
//
// STUBS. Each function names the endpoint that will replace it; screens import
// from `@/data`, never from here or from `data/fixtures/*` directly.

import { PROJECTS } from "./fixtures/projects";
import { after, READ_DELAY_MS } from "./timing";
import type { Project } from "./types";

// STUB: GET /api/projects
export const getProjects = (): Promise<Project[]> =>
  after(PROJECTS, READ_DELAY_MS);

// STUB: GET /api/projects/{projectId}
export const getProject = (projectId: string): Promise<Project | null> =>
  after(PROJECTS.find((p) => p.id === projectId) ?? null, READ_DELAY_MS);
