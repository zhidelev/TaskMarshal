import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, request } from "./api";
import type {
  Agent,
  AgentConfiguration,
  Attempt,
  Project,
  Readiness,
  Repository,
  Task,
  TaskDetail,
  TaskSpecification,
} from "./types";

const splitLines = (value: FormDataEntryValue | null) =>
  String(value ?? "")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);

function Status({ value }: { value: string }) {
  return <span className={`status status-${value}`}>{value.replaceAll("_", " ")}</span>;
}

export function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [configurations, setConfigurations] = useState<AgentConfiguration[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selected, setSelected] = useState<TaskDetail | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [notice, setNotice] = useState("Ready for configuration.");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [nextProjects, nextRepositories, nextAgents, nextConfigurations, nextTasks] =
      await Promise.all([
        api.list<Project>("projects"),
        api.list<Repository>("repositories"),
        api.list<Agent>("agents"),
        api.list<AgentConfiguration>("agent-configurations"),
        api.list<Task>("tasks"),
      ]);
    setProjects(nextProjects);
    setRepositories(nextRepositories);
    setAgents(nextAgents);
    setConfigurations(nextConfigurations);
    setTasks(nextTasks);
  }, []);

  useEffect(() => {
    refresh().catch((error: Error) => setNotice(error.message));
  }, [refresh]);

  async function run(action: () => Promise<void>, success: string) {
    setBusy(true);
    try {
      await action();
      await refresh();
      setNotice(success);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Operation failed");
    } finally {
      setBusy(false);
    }
  }

  async function openTask(id: string) {
    setBusy(true);
    try {
      const [detail, gate] = await Promise.all([
        api.task<TaskDetail>(id),
        api.readiness<Readiness>(id),
      ]);
      setSelected(detail);
      setReadiness(gate);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not load task");
    } finally {
      setBusy(false);
    }
  }

  function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    void run(async () => {
      await api.create<Project>("projects", {
        name: data.get("name"),
        description: data.get("description"),
      });
      form.reset();
    }, "Project created.");
  }

  function createRepository(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    void run(async () => {
      await api.create<Repository>("repositories", {
        project_id: data.get("project_id"),
        name: data.get("name"),
        url: data.get("url"),
        default_branch: data.get("default_branch"),
        credential_ref: data.get("credential_ref") || null,
        available_secret_refs: splitLines(data.get("secret_refs")),
        access_validated: data.get("access_validated") === "on",
      });
      form.reset();
    }, "Repository configuration saved.");
  }

  function createAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    void run(async () => {
      const agent = await api.create<Agent>("agents", {
        name: data.get("name"),
        description: data.get("description"),
      });
      await request<AgentConfiguration>(`/api/v1/agents/${agent.id}/configurations`, {
        method: "POST",
        body: JSON.stringify(agentConfigurationPayload(data)),
      });
      form.reset();
    }, "Agent and immutable configuration v1 created.");
  }

  function versionAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    void run(async () => {
      await request<AgentConfiguration>(
        `/api/v1/agents/${String(data.get("agent_id"))}/configurations`,
        { method: "POST", body: JSON.stringify(agentConfigurationPayload(data)) },
      );
      form.reset();
    }, "New immutable agent configuration version created.");
  }

  function agentConfigurationPayload(data: FormData) {
    return {
      name: data.get("configuration_name"),
      role_eligibility: ["actor", "reviewer"],
      adapter_type: data.get("adapter_type") || "pydantic_ai",
      provider: data.get("provider"),
      model: data.get("model"),
      instructions: data.get("instructions"),
      max_concurrency: Number(data.get("max_concurrency") || 1),
      timeout_seconds: Number(data.get("timeout_seconds") || 1800),
      max_cost_usd: Number(data.get("max_cost_usd") || 0),
      created_by: data.get("created_by"),
    };
  }

  function createTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const repository = repositories.find((item) => item.id === data.get("repository_id"));
    if (!repository) return;
    void run(async () => {
      const task = await api.create<Task>("tasks", {
        project_id: repository.project_id,
        title: data.get("title"),
      });
      await request<TaskSpecification>(`/api/v1/tasks/${task.id}/specifications`, {
        method: "POST",
        body: JSON.stringify(specificationPayload(data)),
      });
      form.reset();
      await openTask(task.id);
    }, "Logical task and specification v1 created.");
  }

  function specificationPayload(data: FormData) {
    return {
      repository_id: data.get("repository_id"),
      base_revision: data.get("base_revision"),
      goal: data.get("goal"),
      acceptance_criteria: splitLines(data.get("acceptance_criteria")),
      verification_commands: splitLines(data.get("verification_commands")),
      constraints: splitLines(data.get("constraints")),
      actor_configuration_id: data.get("agent_configuration_id"),
      reviewer_configuration_id: data.get("agent_configuration_id"),
      limits: {
        timeout_seconds: Number(data.get("timeout_seconds") || 1800),
        max_tokens: Number(data.get("max_tokens") || 100000),
        max_cost_usd: Number(data.get("max_cost_usd") || 10),
      },
      required_secret_refs: splitLines(data.get("required_secret_refs")),
      sandbox_policy: {
        network: data.get("network") || "none",
        writable_paths: ["/workspace"],
        allow_external_mutation: false,
      },
      dependency_ids: [],
      authored_by: data.get("authored_by"),
    };
  }

  function versionTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected?.current_specification) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const previous = selected.current_specification;
    const payload = {
      ...previous,
      goal: data.get("goal"),
      base_revision: data.get("base_revision"),
      acceptance_criteria: splitLines(data.get("acceptance_criteria")),
      verification_commands: splitLines(data.get("verification_commands")),
      authored_by: data.get("authored_by"),
    };
    const {
      id: _id,
      task_id: _taskId,
      version: _version,
      authored_at: _authoredAt,
      content_hash: _contentHash,
      ...command
    } = payload;
    void run(async () => {
      await request<TaskSpecification>(`/api/v1/tasks/${selected.task.id}/specifications`, {
        method: "POST",
        body: JSON.stringify(command),
      });
      await openTask(selected.task.id);
    }, "Authoritative edit saved as a new specification version.");
  }

  function startAttempt() {
    if (!selected || !readiness?.ready) return;
    void run(async () => {
      const attempt = await api.start<Attempt>(selected.task.id);
      setNotice(`Attempt ${attempt.id.slice(0, 8)} started; task remains distinct.`);
      await openTask(selected.task.id);
    }, "Attempt started manually.");
  }

  return (
    <div className="app-shell">
      <header>
        <a className="brand" href="#top"><span>TM</span> TaskMarshal</a>
        <div className="environment"><i /> local control plane</div>
      </header>

      <main id="top">
        <section className="hero">
          <div>
            <p className="eyebrow">Milestone 0.1 · Foundation</p>
            <h1>Logical work stays larger than any single attempt.</h1>
            <p>Configure the control plane, prove readiness, then open a manually driven attempt with an immutable input state.</p>
          </div>
          <div className="chain" aria-label="Task lifecycle chain">
            <b>Task</b><span>→</span><b>Attempt</b><span>→</span><b>Artifact</b><span>→</span><b>Evidence</b>
          </div>
        </section>

        <div className="notice" role="status"><span>{busy ? "Working" : "Status"}</span>{notice}</div>

        <section className="stats">
          <article><small>Projects</small><strong>{projects.length}</strong></article>
          <article><small>Repositories</small><strong>{repositories.length}</strong></article>
          <article><small>Agent configs</small><strong>{configurations.length}</strong></article>
          <article><small>Logical tasks</small><strong>{tasks.length}</strong></article>
        </section>

        <section className="workspace">
          <div className="task-board panel">
            <div className="panel-heading"><div><p className="eyebrow">Operations</p><h2>Task board</h2></div><button className="quiet" onClick={() => void refresh()}>Refresh</button></div>
            {tasks.length === 0 ? <div className="empty">No logical work yet. Complete the setup forms to create specification v1.</div> : (
              <div className="task-list">{tasks.map((task) => (
                <button className="task-row" key={task.id} onClick={() => void openTask(task.id)}>
                  <div><strong>{task.title}</strong><small>work_id · {task.id}</small></div>
                  <div><Status value={task.status} /><small>epoch {task.ownership_epoch}</small></div>
                </button>
              ))}</div>
            )}
          </div>

          <aside className="panel detail">
            {!selected ? <div className="empty"><span className="empty-mark">↗</span>Select a task to inspect its specification, deterministic gate, and attempts.</div> : (
              <>
                <div className="panel-heading"><div><p className="eyebrow">Logical task</p><h2>{selected.task.title}</h2></div><Status value={selected.task.status} /></div>
                <div className="identity"><code>{selected.task.id}</code><span>spec v{selected.current_specification?.version ?? "—"}</span></div>
                {readiness && <div className="gate">
                  <div className="gate-head"><strong>Readiness gate</strong><span>{readiness.satisfied}/{readiness.total}</span></div>
                  <div className="meter"><i style={{ width: `${(readiness.satisfied / readiness.total) * 100}%` }} /></div>
                  <ul>{readiness.requirements.map((item) => <li key={item.code} className={item.satisfied ? "pass" : "fail"}><span>{item.satisfied ? "✓" : "×"}</span><div><code>{item.code}</code>{!item.satisfied && <small>{item.remediation}</small>}</div></li>)}</ul>
                  <button className="primary full" disabled={!readiness.ready || busy} onClick={startAttempt}>Start manual attempt</button>
                </div>}
                <div className="attempts"><h3>Attempts <span>{selected.attempts.length}</span></h3>{selected.attempts.length === 0 ? <p>No attempts. Readiness must pass first.</p> : selected.attempts.map((attempt) => <div className="attempt" key={attempt.id}><div><code>{attempt.id.slice(0, 12)}</code><small>input {attempt.input_state_id.slice(0, 10)} · epoch {attempt.ownership_epoch}</small></div><Status value={attempt.status} /></div>)}</div>
                {selected.current_specification && <details className="version-editor"><summary>Create next specification version</summary><form onSubmit={versionTask}>
                  <label>Goal<textarea name="goal" defaultValue={selected.current_specification.goal} required /></label>
                  <label>Base revision<input name="base_revision" defaultValue={selected.current_specification.base_revision} required /></label>
                  <label>Acceptance criteria<textarea name="acceptance_criteria" defaultValue={selected.current_specification.acceptance_criteria.join("\n")} required /></label>
                  <label>Verification commands<textarea name="verification_commands" defaultValue={selected.current_specification.verification_commands.join("\n")} required /></label>
                  <label>Author<input name="authored_by" defaultValue="operator" required /></label>
                  <button className="primary" disabled={busy}>Save immutable version</button>
                </form></details>}
              </>
            )}
          </aside>
        </section>

        <section className="setup">
          <div className="section-title"><p className="eyebrow">Configuration</p><h2>Foundation setup</h2><p>Each step creates persisted control-plane state. Credential fields accept references only.</p></div>
          <div className="setup-grid">
            <details open><summary><span>01</span> Project</summary><form onSubmit={createProject}>
              <label>Name<input name="name" placeholder="TaskMarshal" required /></label>
              <label>Description<textarea name="description" placeholder="Reliable coding-agent operations" /></label>
              <button className="primary" disabled={busy}>Create project</button>
            </form></details>

            <details open><summary><span>02</span> Repository</summary><form onSubmit={createRepository}>
              <label>Project<select name="project_id" required><option value="">Select…</option>{projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              <label>Name<input name="name" placeholder="taskmarshal" required /></label>
              <label>Repository URL<input name="url" placeholder="https://github.com/org/repo.git" required /></label>
              <div className="two"><label>Default branch<input name="default_branch" defaultValue="main" required /></label><label>Credential ref<input name="credential_ref" placeholder="vault://…" /></label></div>
              <label>Available secret refs<textarea name="secret_refs" placeholder="One reference per line" /></label>
              <label className="check"><input type="checkbox" name="access_validated" /> Access validated by control plane</label>
              <button className="primary" disabled={busy}>Save repository</button>
            </form></details>

            <details open><summary><span>03</span> Agent</summary><form onSubmit={createAgent}>
              <label>Name<input name="name" placeholder="Foundation actor" required /></label>
              <label>Description<input name="description" placeholder="Actor and reviewer eligible" /></label>
              <AgentFields />
              <button className="primary" disabled={busy}>Create agent + config</button>
            </form>
            {agents.length > 0 && <form className="subform" onSubmit={versionAgent}><h3>Version existing agent</h3><label>Agent<select name="agent_id" required><option value="">Select…</option>{agents.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><AgentFields /><button className="quiet" disabled={busy}>Create next config version</button></form>}
            </details>

            <details open><summary><span>04</span> Versioned task</summary><form onSubmit={createTask}>
              <label>Repository<select name="repository_id" required><option value="">Select…</option>{repositories.map((item) => <option key={item.id} value={item.id}>{item.name}{item.validated_at ? " · validated" : " · unvalidated"}</option>)}</select></label>
              <label>Title<input name="title" placeholder="Implement readiness gate" required /></label>
              <label>Goal<textarea name="goal" required /></label>
              <label>Acceptance criteria<textarea name="acceptance_criteria" placeholder="One criterion per line" required /></label>
              <label>Verification commands<textarea name="verification_commands" placeholder="pytest tests/unit" required /></label>
              <label>Constraints<textarea name="constraints" placeholder="One constraint per line" /></label>
              <label>Agent configuration<select name="agent_configuration_id" required><option value="">Select…</option>{configurations.map((item) => <option key={item.id} value={item.id}>{agents.find((agent) => agent.id === item.agent_id)?.name ?? "Agent"} · {item.name} · v{item.version} · {item.model}</option>)}</select></label>
              <div className="two"><label>Base revision<input name="base_revision" placeholder="commit SHA" required /></label><label>Author<input name="authored_by" defaultValue="operator" required /></label></div>
              <div className="three"><label>Timeout (s)<input type="number" name="timeout_seconds" defaultValue="1800" min="1" /></label><label>Max tokens<input type="number" name="max_tokens" defaultValue="100000" min="1" /></label><label>Max cost ($)<input type="number" name="max_cost_usd" defaultValue="10" min="0" step="0.01" /></label></div>
              <label>Required secret refs<textarea name="required_secret_refs" placeholder="References only; never secret values" /></label>
              <label>Sandbox network<select name="network"><option value="none">None</option><option value="allowlist">Allowlist</option></select></label>
              <button className="primary" disabled={busy}>Create task + specification v1</button>
            </form></details>
          </div>
        </section>
      </main>
      <footer><span>TaskMarshal 0.1</span><a href="http://localhost:8000/docs">OpenAPI</a><a href="http://localhost:8080">Temporal UI</a></footer>
    </div>
  );
}

function AgentFields() {
  return <>
    <label>Configuration name<input name="configuration_name" defaultValue="Default" required /></label>
    <div className="two"><label>Adapter<select name="adapter_type"><option value="pydantic_ai">PydanticAI</option><option value="manual">Manual</option></select></label><label>Provider<input name="provider" defaultValue="openai" required /></label></div>
    <label>Model<input name="model" placeholder="openai:gpt-5" required /></label>
    <label>Instructions<textarea name="instructions" placeholder="System instructions" required /></label>
    <div className="three"><label>Concurrency<input type="number" name="max_concurrency" defaultValue="1" min="1" /></label><label>Timeout (s)<input type="number" name="timeout_seconds" defaultValue="1800" min="1" /></label><label>Cost cap ($)<input type="number" name="max_cost_usd" defaultValue="10" min="0" step="0.01" /></label></div>
    <label>Created by<input name="created_by" defaultValue="operator" required /></label>
  </>;
}
