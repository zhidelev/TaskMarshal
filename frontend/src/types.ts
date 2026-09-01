export type Project = { id: string; name: string; description: string };
export type Repository = {
  id: string;
  project_id: string;
  name: string;
  url: string;
  default_branch: string;
  validated_at: string | null;
};
export type Agent = { id: string; name: string; description: string };
export type AgentConfiguration = {
  id: string;
  agent_id: string;
  version: number;
  role_eligibility: string[];
  provider: string;
  model: string;
  max_concurrency: number;
};
export type Task = {
  id: string;
  project_id: string;
  title: string;
  status: string;
  ownership_epoch: number;
  current_specification_id: string | null;
};
export type TaskSpecification = {
  id: string;
  version: number;
  repository_id: string;
  goal: string;
  base_revision: string;
  acceptance_criteria: string[];
  verification_commands: string[];
  constraints: string[];
  actor_configuration_id: string;
  reviewer_configuration_id: string;
  limits: { timeout_seconds: number; max_tokens: number; max_cost_usd: number };
  required_secret_refs: string[];
  sandbox_policy: { network: "none" | "allowlist"; writable_paths: string[]; allow_external_mutation: false };
  dependency_ids: string[];
  authored_by: string;
  authored_at: string;
};
export type Attempt = {
  id: string;
  status: string;
  input_state_id: string;
  ownership_epoch: number;
  started_at: string;
};
export type TaskDetail = {
  task: Task;
  current_specification: TaskSpecification | null;
  specification_history: TaskSpecification[];
  attempts: Attempt[];
};
export type Readiness = {
  work_id: string;
  ready: boolean;
  satisfied: number;
  total: number;
  requirements: { code: string; satisfied: boolean; remediation: string }[];
};
