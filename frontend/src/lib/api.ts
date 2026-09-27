import type {
  AITwin,
  AnalyzeRequest,
  AnalyzeResponse,
  AssignmentChange,
  EmployeeInput,
  EmployeeSummary,
  ImportResult,
  ImportReport,
  Mode,
  PlaneMember,
  PlaneProjectSummary,
  PlaneStatus,
  ProjectDetail,
  ProjectSettings,
  ProjectSummary,
  SimulateResponse,
  TaskInput,
  SlackImportMember,
  SlackMember,
  SlackStatus,
} from "./types";

export type ValidationIssue = { loc: (string | number)[]; msg: string };

export class ApiError extends Error {
  constructor(message: string, public readonly issues: ValidationIssue[] = []) {
    super(message);
  }
}

export function formatApiError(data: unknown, status: number): string {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: ValidationIssue) => `${(d.loc ?? []).filter((p) => p !== "body").join(".")}: ${d.msg}`)
      .join("; ");
  }
  return typeof detail === "string" ? detail : `Request failed (HTTP ${status})`;
}

/** Turns row-level validation errors (loc: body.<list>.<index>.<field>) into readable lines. */
export function describeRowIssues(issues: ValidationIssue[], listKey: string, rowName: (index: number) => string | undefined): string[] {
  return issues.map((issue) => {
    const [, key, index, ...field] = issue.loc;
    if (key !== listKey || typeof index !== "number") return `${issue.loc.filter((p) => p !== "body").join(".")}: ${issue.msg}`;
    const name = rowName(index);
    return `Row ${index + 1}${name ? ` (${name})` : ""}${field.length ? ` · ${field.join(".")}` : ""}: ${issue.msg}`;
  });
}

async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(`/api/${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(formatApiError(data, res.status), Array.isArray(detail) ? (detail as ValidationIssue[]) : []);
  }
  return data as T;
}

const employee = (id: string) => `employees/${encodeURIComponent(id)}`;
const project = (id: string) => `projects/${encodeURIComponent(id)}`;

export const api = {
  analyze: (body: AnalyzeRequest) => request<AnalyzeResponse>("ai-twins/analyze", "POST", body),
  listEmployees: () => request<EmployeeSummary[]>("employees"),
  createEmployee: (input: EmployeeInput) => request<EmployeeSummary>("employees", "POST", input),
  updateEmployee: (id: string, input: EmployeeInput) => request<EmployeeSummary>(employee(id), "PUT", input),
  deleteEmployee: (id: string) => request<void>(employee(id), "DELETE"),
  bulkDeleteEmployees: (ids: string[]) =>
    request<{ deleted: string[]; not_found: string[] }>("employees/bulk-delete", "POST", { employee_ids: ids }),
  importEmployees: (employees: unknown[], generateTwins: boolean) =>
    request<ImportResult>("employees/import", "POST", { employees, generate_twins: generateTwins }),
  generateTwin: (id: string) => request<AITwin>(`${employee(id)}/generate-twin`, "POST"),
  getTwin: (id: string) => request<AITwin>(`${employee(id)}/twin`),
  listProjects: () => request<ProjectSummary[]>("projects"),
  getProject: (pid: string) => request<ProjectDetail>(project(pid)),
  createTask: (pid: string, input: TaskInput) => request<ProjectDetail>(`${project(pid)}/tasks`, "POST", input),
  updateTask: (pid: string, id: string, input: TaskInput) => request<ProjectDetail>(`${project(pid)}/tasks/${encodeURIComponent(id)}`, "PUT", input),
  setTaskOverrides: (pid: string, id: string, overrides: { task_type: string | null; effort_hours: number | null }) =>
    request<ProjectDetail>(`${project(pid)}/tasks/${encodeURIComponent(id)}/overrides`, "PUT", overrides),
  deleteTask: (pid: string, id: string) => request<ProjectDetail>(`${project(pid)}/tasks/${encodeURIComponent(id)}`, "DELETE"),
  clearTasks: (pid: string) => request<ProjectDetail>(`${project(pid)}/tasks`, "DELETE"),
  loadSampleBacklog: (pid: string) => request<ProjectDetail>(`${project(pid)}/sample`, "POST"),
  updateSettings: (pid: string, settings: ProjectSettings) => request<ProjectDetail>(`${project(pid)}/settings`, "PUT", settings),
  setAssignment: (pid: string, changes: AssignmentChange[]) => request<ProjectDetail>(`${project(pid)}/assignment`, "PUT", { changes }),
  autoAssign: (pid: string) => request<ProjectDetail>(`${project(pid)}/auto-assign`, "POST"),
  syncProject: (pid: string) => request<{ report: ImportReport; project: ProjectDetail }>(`${project(pid)}/sync`, "POST"),
  deleteProject: (pid: string) => request<void>(project(pid), "DELETE"),
  simulate: (pid: string, mode: Mode, targetEmployeeId?: string | null) =>
    request<SimulateResponse>(`${project(pid)}/simulate`, "POST", { mode, target_employee_id: targetEmployeeId ?? null }),
  planeStatus: () => request<PlaneStatus>("integrations/plane/status"),
  planeConnect: (config: { base_url: string; api_key: string; workspace_slug: string }) =>
    request<PlaneStatus>("integrations/plane/connect", "POST", config),
  planeDisconnect: () => request<void>("integrations/plane/connect", "DELETE"),
  planeProjects: () => request<PlaneProjectSummary[]>("plane/projects"),
  planeImport: (planeProjectId: string) => request<ImportReport>(`plane/projects/${encodeURIComponent(planeProjectId)}/import`, "POST"),
  planeMembers: (refresh = true) => request<PlaneMember[]>(`plane/members?refresh=${refresh}`),
  planeMapMember: (plane_user_id: string, action: "match" | "leave_unassigned" | "clear", employee_id: string | null = null) =>
    request<PlaneMember[]>("plane/members/mapping", "PUT", { plane_user_id, action, employee_id }),
  slackStatus: () => request<SlackStatus>("integrations/slack/status"),
  slackMembers: () => request<SlackMember[]>("integrations/slack/members"),
  slackImport: (members: SlackImportMember[], generateTwins: boolean) =>
    request<ImportResult>("integrations/slack/import", "POST", { members, generate_twins: generateTwins }),
};
