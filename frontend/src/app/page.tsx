import Dashboard from "@/components/Dashboard";
import { fetchBackendJson } from "@/lib/backend";
import type { EmployeeSummary, ProjectDetail, ProjectSummary, SimulateResponse } from "@/lib/types";

const DEFAULT_PROJECT = "local";

export default async function Home() {
  const [team, projects, project, simulation] = await Promise.all([
    fetchBackendJson<EmployeeSummary[]>(["employees"]),
    fetchBackendJson<ProjectSummary[]>(["projects"]),
    fetchBackendJson<ProjectDetail>(["projects", DEFAULT_PROJECT]),
    fetchBackendJson<SimulateResponse>(["projects", DEFAULT_PROJECT, "simulate"], "POST", { mode: "status_snapshot" }),
  ]);

  return (
    <Dashboard
      initialTeam={team.data}
      initialProjects={projects.data ?? []}
      initialProject={project.data}
      initialSimulation={simulation.data}
      initialError={team.error ?? projects.error ?? project.error ?? simulation.error}
    />
  );
}
