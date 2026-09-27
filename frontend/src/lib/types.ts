export type Mode =
  | "optimize_fastest"
  | "resolve_burnout_all"
  | "resolve_burnout_single"
  | "status_snapshot";

export type RiskLevel = "Normal" | "Warning" | "Critical";

export interface Assignment {
  task_id: string;
  assigned_employee_id: string;
}

export interface Task {
  task_id: string;
  task_type: string;
  dependencies: string[];
  effort_estimate_hours: number;
  deadline: string | null;
}

export interface Employee {
  employee_id: string;
  name: string;
  current_role: string;
  available_roles: string[];
  historical_velocity: number;
  current_workload_hours: number;
  overtime_hours_last_7d: number;
  autonomy_score: number;
  cognitive_load_factor: number;
  historical_task_velocity?: Record<string, number> | null;
  weekly_available_hours?: number | null;
}

export interface Scenario {
  current_assignment: Assignment[];
  backlog: Task[];
  employees: Employee[];
}

export interface AnalyzeRequest extends Scenario {
  mode: Mode;
  target_employee_id?: string | null;
}

export interface Rotation {
  rotation_id: string;
  total_completion_time_hours: number;
  assignments: Assignment[];
}

export interface DeltaMetrics {
  velocity_boost_pct: number;
  burnout_mitigation_pct: number | null;
  milestone_time_saved_hours: number;
}

export interface EmployeeResult {
  employee_id: string;
  stamina: number;
  stress_score: number;
  risk_level: RiskLevel;
  compatibility_pct: number | null;
  velocity_tasks_per_day: number | null;
  primary_contributing_factors: string[];
}

export interface ActionableSwap {
  swap_between: [string, string];
  tasks_affected: string[];
  rationale: string;
  expected_stress_reduction_pct: number;
}

export interface AnalyzeResponse {
  mode: Mode;
  rotations_evaluated: number;
  rotations_ranked: Rotation[];
  delta_metrics: DeltaMetrics | null;
  employees: EmployeeResult[];
  recommendations: {
    role_swap_required: boolean;
    actionable_swaps: ActionableSwap[];
  };
  warnings: string[];
}

export type TwinStatus = "not_generated" | "generated" | "outdated";

export interface EmployeeInput {
  name: string;
  current_role: string;
  skills: string[];
  experience_years: number;
  available_roles: string[];
  current_workload_hours: number;
  weekly_available_hours: number;
}

export interface EmployeeSummary extends EmployeeInput {
  employee_id: string;
  source: "manual" | "slack" | "json_import";
  external_ref: string | null;
  twin_status: TwinStatus;
}

export interface ImportResult {
  created: EmployeeSummary[];
  skipped: { ref: string; name: string; reason: string }[];
}

export interface SlackStatus {
  configured: boolean;
  connected: boolean;
  workspace: string | null;
  error: string | null;
}

export interface SlackMember {
  slack_user_id: string;
  name: string;
  title: string | null;
  existing_employee_id: string | null;
}

export interface SlackImportMember {
  slack_user_id: string;
  current_role: string | null;
  skills: string[];
  experience_years: number;
  available_roles: string[];
  current_workload_hours: number;
  weekly_available_hours: number;
}

export interface AITwin extends Employee {
  historical_task_velocity: Record<string, number>;
  skills: string[];
  experience_years: number;
  role_compatibility: { role: string; matched_task_types: string[]; compatibility_pct: number | null }[];
  task_type_fit: { task_type: string; matched_signals: string[]; estimated_speed: number; compatibility_pct: number }[];
  simulation_profile: {
    current_workload_hours: number;
    weekly_available_hours: number;
    capacity_used_pct: number;
    autonomy_pct: number;
    cognitive_load_pct: number;
  };
  parameter_basis: "estimated_defaults";
  parameter_notes: Record<string, string>;
  generator_version: string;
  source_fingerprint: string;
}

export interface TaskInput {
  title: string;
  task_type: string;
  effort_estimate_hours: number;
  dependencies: string[];
  deadline: string | null;
}

export interface TaskView {
  task_id: string;
  title: string;
  description: string | null;
  source: "local" | "plane";
  source_task_id: string | null;
  task_type: string | null;
  task_type_origin: "manual" | "label" | null;
  task_type_candidates: string[];
  task_type_override: string | null;
  estimate_kind: "hours" | "time" | "points" | "category" | null;
  estimate_raw: string | null;
  estimate_value: number | null;
  effort_hours_override: number | null;
  dependencies: string[];
  external_dependency_ids: string[];
  relations_synced: boolean;
  deadline: string | null;
  start_date: string | null;
  priority: string | null;
  status: string | null;
  status_group: string | null;
  cycle_id: string | null;
  source_assignee_ids: string[];
  effective_task_type: string | null;
  task_type_source: "manual" | "label" | "override" | null;
  effort_estimate_hours: number | null;
  effort_source: "manual" | "plane_time" | "points" | "override" | null;
  assigned_employee_id: string | null;
  assignment_source: "manual" | "plane" | null;
  in_simulation: boolean;
  issues: string[];
}

export interface Cycle {
  cycle_id: string;
  name: string;
  start_date: string | null;
  end_date: string | null;
  status: string | null;
}

export interface ProjectSettings {
  hours_per_point: number | null;
  cycle_id: string | null;
  include_completed: boolean;
}

export interface ProjectSummary {
  project_id: string;
  source: "local" | "plane";
  source_project_id: string | null;
  name: string;
  identifier: string | null;
  description: string | null;
  settings: ProjectSettings;
  cycles: Cycle[];
  last_synced_at: string | null;
  sync_notes: string[];
  task_count: number;
  open_task_count: number;
  simulated_task_count: number;
  attention_count: number;
  current_cycle: Cycle | null;
}

export interface ProjectDetail extends ProjectSummary {
  tasks: TaskView[];
  task_types: string[];
}

export interface AssignmentChange {
  task_id: string;
  assigned_employee_id: string | null;
  follow_source?: boolean;
}

export interface SimulateResponse {
  analysis: AnalyzeResponse;
  payload: AnalyzeRequest;
  context: {
    project_id: string;
    project_name: string;
    employees: { employee_id: string; name: string; current_role: string; twin_status: TwinStatus }[];
    excluded_employees: { employee_id: string; name: string; reason: string }[];
    tasks: TaskView[];
    excluded_tasks: { task_id: string; title: string; reason: string }[];
    unassigned_task_ids: string[];
  };
}

export interface PlaneStatus {
  configured: boolean;
  connected: boolean;
  config_source: "env" | "saved" | null;
  base_url: string | null;
  workspace_slug: string | null;
  api_key_hint: string | null;
  user: string | null;
  error: string | null;
}

export interface PlaneProjectSummary {
  plane_project_id: string;
  name: string;
  identifier: string | null;
  description: string | null;
  imported_project_id: string | null;
}

export interface ImportReport {
  project_id: string;
  created: number;
  updated: number;
  removed: number;
  notes: string[];
}

export interface PlaneMember {
  plane_user_id: string;
  display_name: string;
  email: string | null;
  status: "matched" | "left_unassigned" | "unmatched";
  employee_id: string | null;
  suggested_employee_id: string | null;
  assigned_task_count: number;
}

export const MODE_LABELS: Record<Mode, string> = {
  status_snapshot: "Status snapshot",
  optimize_fastest: "Optimize for fastest delivery",
  resolve_burnout_all: "Resolve all burnout risks",
  resolve_burnout_single: "Resolve burnout (single twin)",
};
