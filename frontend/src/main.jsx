import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BookmarkPlus,
  BarChart3,
  CheckCircle2,
  Clock3,
  Database,
  Flame,
  Gauge,
  History,
  Lightbulb,
  LineChart,
  Loader2,
  Radar,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart as ReLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import "./styles/app.css";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const starterPrompts = [
  "Show me new client conversations started each month this year",
  "Compare average response time by team member over the last 90 days",
  "Clients who haven't had any contact in over 30 days",
  "Why are we getting fewer new clients this month?",
  "Is the team keeping up with demand?",
  "Are there any unusual patterns in conversations lately?",
];

const roleGroups = [
  { label: "Ops", prompt: "Is the team keeping up with demand?" },
  { label: "Sales", prompt: "Who closed the most conversations last month?" },
  { label: "Leadership", prompt: "What's been our best month this year and why?" },
];

const savedStorageKey = "issa-insight-saved-investigations-v1";
const chartPalette = ["#0f766e", "#2563eb", "#b45309", "#7c3aed", "#db2777", "#475569"];

function App() {
  const [activeView, setActiveView] = useState("ask");
  const [question, setQuestion] = useState(starterPrompts[3]);
  const [answer, setAnswer] = useState(seedAnswer);
  const [radar, setRadar] = useState(null);
  const [riskQueue, setRiskQueue] = useState(null);
  const [schema, setSchema] = useState(null);
  const [conversationHistory, setConversationHistory] = useState([]);
  const [savedInvestigations, setSavedInvestigations] = useState(() => loadSavedInvestigations());
  const [loading, setLoading] = useState(false);
  const [intelLoading, setIntelLoading] = useState(false);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    loadIntelligence();
    loadSchema();
  }, []);

  async function submit(nextQuestion = question) {
    setActiveView("ask");
    setQuestion(nextQuestion);
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: nextQuestion, history: conversationHistory.slice(-4) }),
      });
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body.detail || "The query failed.");
      }
      const result = await response.json();
      setAnswer(result);
      setConversationHistory((items) => [...items, compactHistoryItem(result)].slice(-6));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadJson(path) {
    const response = await fetch(`${API_BASE}${path}`);
    if (!response.ok) {
      const body = await response.json();
      throw new Error(body.detail || "The request failed.");
    }
    return response.json();
  }

  async function loadIntelligence() {
    setIntelLoading(true);
    try {
      const [radarResult, riskResult] = await Promise.all([
        loadJson("/api/intelligence/radar"),
        loadJson("/api/intelligence/risk-queue"),
      ]);
      setRadar(radarResult);
      setRiskQueue(riskResult);
    } catch (err) {
      setError(err.message);
    } finally {
      setIntelLoading(false);
    }
  }

  async function loadSchema() {
    setSchemaLoading(true);
    try {
      const schemaResult = await loadJson("/api/schema/summary");
      setSchema(schemaResult);
    } catch (err) {
      setError(err.message);
    } finally {
      setSchemaLoading(false);
    }
  }

  function focusRadar() {
    if (!radar) return;
    setAnswer({
      mode: "radar",
      title: radar.title,
      diagnosis: radar.summary,
      confidence: "High",
      caveats: ["Radar compares recent operating windows and may overstate movement when the current month is incomplete."],
      recommended_actions: [
        "Open the highest-severity signal and ask a follow-up by channel, assignee, or lifecycle.",
        "Confirm whether current-month data is complete before escalating a decline.",
      ],
      plan: radar.signals.map((signal) => ({
        title: signal.name,
        rationale: signal.detail,
        status: signal.severity,
      })),
      visualizations: radar.signals.map((signal) => ({
        title: signal.name,
        type: signal.data?.length > 1 ? "bar" : "metric",
        data: signal.data,
      })),
      evidence: ["Anomaly Radar runs deterministic checks before the user asks a question."],
      sql: [],
    });
    setActiveView("ask");
  }

  function focusRiskQueue() {
    if (!riskQueue) return;
    setAnswer({
      mode: "risk",
      title: riskQueue.title,
      diagnosis: riskQueue.summary,
      confidence: "High",
      caveats: ["Risk scoring is deterministic and should be treated as a prioritization queue, not a churn prediction model."],
      recommended_actions: [
        "Review the top 10 clients and reassign any stale handed-off conversations.",
        "Ask a follow-up to break risk down by assignee or current_step.",
      ],
      plan: [
        {
          title: "Risk scoring",
          rationale:
            "Scores active clients using staleness, blocked state, response imbalance, emergency flag, assignment coverage, and AI-disabled state.",
          status: "complete",
        },
      ],
      visualizations: [
        {
          title: "Highest-risk clients",
          type: "table",
          data: riskQueue.clients,
        },
      ],
      evidence: ["Client Risk Queue is a transparent deterministic score, not model judgment."],
      sql: [],
    });
    setActiveView("ask");
  }

  function saveCurrentInvestigation() {
    const saved = {
      id: `${Date.now()}`,
      savedAt: new Date().toISOString(),
      question: answer.question || question,
      answer,
    };
    setSavedInvestigations((items) => {
      const next = [saved, ...items.filter((item) => item.question !== saved.question)].slice(0, 12);
      localStorage.setItem(savedStorageKey, JSON.stringify(next));
      return next;
    });
  }

  function runRecommendedAction(action) {
    submit(`Follow up on this recommended action: ${action}. Use the prior investigation context, show supporting data, and recommend the next operational step.`);
  }

  function openSavedInvestigation(item) {
    setAnswer(item.answer);
    setQuestion(item.question);
    setActiveView("ask");
  }

  function deleteSavedInvestigation(id) {
    setSavedInvestigations((items) => {
      const next = items.filter((item) => item.id !== id);
      localStorage.setItem(savedStorageKey, JSON.stringify(next));
      return next;
    });
  }

  return (
    <main className="app-shell">
      <Sidebar
        activeView={activeView}
        onNavigate={setActiveView}
        onPick={submit}
        onRadar={focusRadar}
        onRisk={focusRiskQueue}
        savedInvestigations={savedInvestigations}
        onOpenSaved={openSavedInvestigation}
        onDeleteSaved={deleteSavedInvestigation}
      />
      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>{viewTitle(activeView)}</h1>
            <p>{viewDescription(activeView)}</p>
          </div>
          <div className="status-pill">
            <ShieldCheck size={16} />
            Read-only SQL
          </div>
        </header>

        {error && <div className="error-banner page-error">{error}</div>}

        {activeView === "ask" && (
          <AskView
            question={question}
            setQuestion={setQuestion}
            loading={loading}
            answer={answer}
            history={conversationHistory}
            onSubmit={submit}
            onSave={saveCurrentInvestigation}
            onAction={runRecommendedAction}
          />
        )}

        {activeView === "radar" && (
          <RadarPage radar={radar} loading={intelLoading} onRefresh={loadIntelligence} onAnalyze={focusRadar} />
        )}

        {activeView === "risk" && (
          <RiskQueuePage riskQueue={riskQueue} loading={intelLoading} onRefresh={loadIntelligence} onAnalyze={focusRiskQueue} />
        )}

        {activeView === "schema" && (
          <SchemaPage schema={schema} loading={schemaLoading} onRefresh={loadSchema} />
        )}
      </section>
    </main>
  );
}

function Sidebar({ activeView, onNavigate, onPick, savedInvestigations, onOpenSaved, onDeleteSaved }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">I</div>
        <div>
          <strong>Issa Insight</strong>
          <span>Conversation intelligence</span>
        </div>
      </div>

      <nav>
        <button className={activeView === "ask" ? "nav-active" : ""} onClick={() => onNavigate("ask")}>
          <Activity size={17} />
          Ask
        </button>
        <button className={activeView === "radar" ? "nav-active" : ""} onClick={() => onNavigate("radar")}>
          <AlertTriangle size={17} />
          Anomaly Radar
        </button>
        <button className={activeView === "risk" ? "nav-active" : ""} onClick={() => onNavigate("risk")}>
          <Clock3 size={17} />
          Client Risk Queue
        </button>
        <button className={activeView === "schema" ? "nav-active" : ""} onClick={() => onNavigate("schema")}>
          <Database size={17} />
          Schema
        </button>
      </nav>

      <div className="sidebar-section">
        <h2>Role prompts</h2>
        {roleGroups.map((item) => (
          <button className="role-prompt" key={item.label} onClick={() => onPick(item.prompt)}>
            <span>{item.label}</span>
            {item.prompt}
          </button>
        ))}
      </div>

      <div className="sidebar-section saved-section">
        <h2>Saved</h2>
        {savedInvestigations.length === 0 && <p>No saved investigations yet.</p>}
        {savedInvestigations.map((item) => (
          <div className="saved-row" key={item.id}>
            <button onClick={() => onOpenSaved(item)}>
              <span>{new Date(item.savedAt).toLocaleDateString()}</span>
              {item.answer.title}
            </button>
            <button className="icon-button" onClick={() => onDeleteSaved(item.id)} aria-label="Delete saved investigation">
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}

function AskView({ question, setQuestion, loading, answer, history, onSubmit, onSave, onAction }) {
  return (
    <>
      <section className="ask-panel">
        <div className="ask-input">
          <Search size={20} />
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") onSubmit();
            }}
            placeholder="Ask a business question"
          />
          <button onClick={() => onSubmit()} disabled={loading}>
            {loading ? <Loader2 className="spin" size={18} /> : <Sparkles size={18} />}
            Analyze
          </button>
        </div>
        <div className="prompt-row">
          {starterPrompts.slice(0, 4).map((prompt) => (
            <button key={prompt} onClick={() => onSubmit(prompt)}>
              {prompt}
            </button>
          ))}
        </div>
      </section>

      <FollowUpMemory history={history} onPick={onSubmit} />

      <section className="content-grid">
        <section className="answer-column">
          <ResultHeader answer={answer} />
          <AnswerGuidance answer={answer} onSave={onSave} onAction={onAction} />
          <InvestigationPlan plan={answer.plan} />
          <VisualizationGrid visualizations={answer.visualizations} />
        </section>
        <EvidencePanel answer={answer} />
      </section>
    </>
  );
}

function FollowUpMemory({ history, onPick }) {
  if (!history.length) return null;
  return (
    <section className="memory-strip">
      <div>
        <History size={16} />
        <strong>Follow-up memory</strong>
        <span>{history.length} question{history.length === 1 ? "" : "s"} in context</span>
      </div>
      <button onClick={() => onPick("Break that down by channel and explain the biggest driver")}>
        Break that down by channel
      </button>
      <button onClick={() => onPick("What should the team do next based on this?")}>
        What should we do next?
      </button>
    </section>
  );
}

function ProactiveIntel({ radar, riskQueue, loading, onRadar, onRisk, onRefresh }) {
  const topSignals = radar?.signals?.slice(0, 3) || [];
  const topClients = riskQueue?.clients?.slice(0, 4) || [];

  return (
    <section className="intel-grid">
      <article className="intel-panel">
        <div className="intel-heading">
          <div>
            <span>Anomaly Radar</span>
            <h2>{radar?.summary || "Scanning operating signals"}</h2>
          </div>
          <button onClick={onRadar} disabled={!radar}>
            <Radar size={16} />
            Open
          </button>
        </div>
        <div className="signal-list">
          {loading && <div className="small-muted">Loading live signals...</div>}
          {topSignals.map((signal) => (
            <div className={`signal-row severity-${signal.severity}`} key={signal.name}>
              <strong>{signal.name}</strong>
              <span>{signal.metric}</span>
              <p>{signal.detail}</p>
            </div>
          ))}
        </div>
      </article>

      <article className="intel-panel">
        <div className="intel-heading">
          <div>
            <span>Client Risk Queue</span>
            <h2>{riskQueue?.summary || "Ranking clients by operational risk"}</h2>
          </div>
          <button onClick={onRisk} disabled={!riskQueue}>
            <Flame size={16} />
            Open
          </button>
        </div>
        <div className="risk-mini-list">
          {loading && <div className="small-muted">Loading risk queue...</div>}
          {topClients.map((client) => (
            <div className="risk-mini-row" key={client.contact_id}>
              <div>
                <strong>{client.contact_name || `Contact ${client.contact_id}`}</strong>
                <span>{client.status} · {client.assignee}</span>
              </div>
              <b>{client.risk_score}</b>
            </div>
          ))}
        </div>
        <button className="text-button" onClick={onRefresh}>
          Refresh intelligence
        </button>
      </article>
    </section>
  );
}

function RadarPage({ radar, loading, onRefresh, onAnalyze }) {
  const signals = radar?.signals || [];
  return (
    <section className="page-stack">
      <section className="page-hero">
        <div>
          <div className="mode-label">Proactive monitoring</div>
          <h2>{radar?.title || "Anomaly Radar"}</h2>
          <p>{radar?.summary || "Scanning recent conversation, response, and demand patterns for unusual movement."}</p>
        </div>
        <div className="page-actions">
          <button onClick={onRefresh}>
            <Radar size={16} />
            Refresh
          </button>
          <button onClick={onAnalyze} disabled={!radar}>
            <Sparkles size={16} />
            Analyze in Ask
          </button>
        </div>
      </section>

      <section className="signal-page-grid">
        {loading && <div className="small-muted">Loading live signals...</div>}
        {signals.map((signal) => (
          <article className={`signal-card severity-${signal.severity}`} key={signal.name}>
            <div>
              <span>{signal.severity}</span>
              <h2>{signal.name}</h2>
            </div>
            <strong>{signal.metric}</strong>
            <p>{signal.detail}</p>
            <Chart viz={{ title: signal.name, type: signal.data?.length > 1 ? "bar" : "metric", data: signal.data }} />
          </article>
        ))}
      </section>
    </section>
  );
}

function RiskQueuePage({ riskQueue, loading, onRefresh, onAnalyze }) {
  const clients = riskQueue?.clients || [];
  return (
    <section className="page-stack">
      <section className="page-hero">
        <div>
          <div className="mode-label">Operational queue</div>
          <h2>{riskQueue?.title || "Client Risk Queue"}</h2>
          <p>{riskQueue?.summary || "Ranking clients by stale contact, blocked status, response imbalance, and coverage gaps."}</p>
        </div>
        <div className="page-actions">
          <button onClick={onRefresh}>
            <Flame size={16} />
            Refresh
          </button>
          <button onClick={onAnalyze} disabled={!riskQueue}>
            <Sparkles size={16} />
            Analyze in Ask
          </button>
        </div>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <Clock3 size={18} />
          <h2>Highest-priority clients</h2>
        </div>
        {loading && <div className="small-muted">Loading risk queue...</div>}
        <div className="risk-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Client</th>
                <th>Score</th>
                <th>Status</th>
                <th>Assignee</th>
                <th>Last contact</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((client) => (
                <tr key={client.contact_id}>
                  <td>{client.contact_name || `Contact ${client.contact_id}`}</td>
                  <td><strong>{client.risk_score}</strong></td>
                  <td>{client.status}</td>
                  <td>{client.assignee}</td>
                  <td>{formatDate(client.last_contact_at)}</td>
                  <td>{riskReason(client)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}

function SchemaPage({ schema, loading, onRefresh }) {
  const tables = Object.entries(schema?.tables || {});
  return (
    <section className="page-stack">
      <section className="page-hero">
        <div>
          <div className="mode-label">Data map</div>
          <h2>Live Postgres Schema</h2>
          <p>The same schema context the LLM receives before it plans SQL. This keeps users and reviewers grounded in what the app can actually query.</p>
        </div>
        <div className="page-actions">
          <button onClick={onRefresh}>
            <Database size={16} />
            Refresh schema
          </button>
        </div>
      </section>

      <section className="schema-grid">
        {loading && <div className="small-muted">Loading schema...</div>}
        {tables.map(([tableName, columns]) => (
          <article className="schema-card" key={tableName}>
            <div className="schema-card-heading">
              <Database size={18} />
              <h2>{tableName}</h2>
              <span>{columns.length} columns</span>
            </div>
            <div className="schema-column-list">
              {columns.map((column) => (
                <div className="schema-column" key={`${tableName}-${column.name}`}>
                  <strong>{column.name}</strong>
                  <span>{column.type}</span>
                </div>
              ))}
            </div>
          </article>
        ))}
      </section>
    </section>
  );
}

function ResultHeader({ answer }) {
  return (
    <section className="diagnosis">
      <div className="mode-label">{answer.mode === "investigation" ? "Diagnosis" : "Direct answer"}</div>
      <h2>{answer.title}</h2>
      <p>{answer.diagnosis}</p>
      <div className="kpi-row">
        <Kpi label="Queries run" value={answer.sql?.length || 0} icon={<Database size={18} />} />
        <Kpi label="Evidence blocks" value={answer.evidence?.length || 0} icon={<CheckCircle2 size={18} />} />
        <Kpi label="Output mode" value={answer.mode} icon={<BarChart3 size={18} />} />
      </div>
    </section>
  );
}

function AnswerGuidance({ answer, onSave, onAction }) {
  const actions = answer.recommended_actions || [];
  const caveats = answer.caveats || [];
  return (
    <section className="guidance-grid">
      <article className="guidance-card confidence-card">
        <div className="guidance-title">
          <Gauge size={17} />
          <h2>Confidence</h2>
        </div>
        <strong>{answer.confidence || "Medium"}</strong>
        <p>{confidenceCopy(answer.confidence)}</p>
        <button onClick={onSave}>
          <BookmarkPlus size={16} />
          Save investigation
        </button>
      </article>

      <article className="guidance-card">
        <div className="guidance-title">
          <Lightbulb size={17} />
          <h2>Recommended Actions</h2>
        </div>
        {actions.length ? (
          <div className="action-list">
            {actions.map((item, index) => (
              <button key={index} onClick={() => onAction(item)}>
                <span>{item}</span>
                <ArrowRight size={15} />
              </button>
            ))}
          </div>
        ) : (
          <p>No recommended actions returned yet.</p>
        )}
      </article>

      <article className="guidance-card">
        <div className="guidance-title">
          <AlertTriangle size={17} />
          <h2>Caveats</h2>
        </div>
        {caveats.length ? (
          <ul>{caveats.map((item, index) => <li key={index}>{item}</li>)}</ul>
        ) : (
          <p>No major caveats detected.</p>
        )}
      </article>
    </section>
  );
}

function Kpi({ label, value, icon }) {
  return (
    <div className="kpi">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function InvestigationPlan({ plan = [] }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <LineChart size={18} />
        <h2>Investigation Plan</h2>
      </div>
      <div className="plan-list">
        {plan.map((step, index) => (
          <article key={`${step.title}-${index}`} className="plan-step">
            <div className="step-index">{index + 1}</div>
            <div>
              <strong>{step.title}</strong>
              <p>{step.rationale}</p>
            </div>
            <span>{step.status}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

function VisualizationGrid({ visualizations = [] }) {
  return (
    <section className="viz-grid">
      {visualizations.map((viz, index) => (
        <article key={`${viz.title}-${index}`} className="viz-card">
          <h2>{viz.title}</h2>
          <Chart viz={viz} />
        </article>
      ))}
    </section>
  );
}

function Chart({ viz }) {
  const sourceData = viz.data || [];
  if (!sourceData.length) {
    return <div className="empty-chart">No rows returned yet.</div>;
  }

  const keys = Object.keys(sourceData[0]);
  const xKey = pickDimensionKey(sourceData, keys);
  const categoryKey = pickCategoryKey(sourceData, keys, xKey);
  const primaryMetric = pickMetricKey(sourceData, keys, [xKey, categoryKey]);
  const pivoted = categoryKey && primaryMetric ? pivotSeries(sourceData, xKey, categoryKey, primaryMetric) : null;
  const data = pivoted?.data || normalizeChartData(sourceData);
  const seriesKeys = pivoted?.seriesKeys || pickMetricKeys(data, Object.keys(data[0]), [xKey]).slice(0, 4);
  const tableKeys = keys.slice(0, 10);

  if (viz.type === "metric") {
    return (
      <div className="metric-grid">
        {keys.map((key) => (
          <div className="metric-tile" key={key}>
            <span>{key}</span>
            <strong>{formatValue(data[0][key])}</strong>
          </div>
        ))}
      </div>
    );
  }

  if (viz.type === "table") {
    return (
      <div className="table-wrap">
        <table>
          <thead>
            <tr>{tableKeys.map((key) => <th key={key}>{prettyLabel(key)}</th>)}</tr>
          </thead>
          <tbody>
            {sourceData.slice(0, 10).map((row, index) => (
              <tr key={index}>{tableKeys.map((key) => <td key={key}>{formatValue(row[key])}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (!seriesKeys.length) {
    return <div className="empty-chart">No numeric metrics available to chart.</div>;
  }

  if (viz.type === "bar") {
    return (
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data}>
          <CartesianGrid stroke="#e7ebef" vertical={false} />
          <XAxis dataKey={xKey} tick={{ fill: "#617080", fontSize: 12 }} tickFormatter={shortTick} />
          <YAxis tick={{ fill: "#617080", fontSize: 12 }} tickFormatter={compactNumber} />
          <Tooltip formatter={(value, name) => [formatValue(value), prettyLabel(name)]} labelFormatter={formatValue} />
          {seriesKeys.length > 1 && <Legend formatter={prettyLabel} />}
          {seriesKeys.map((key, index) => (
            <Bar
              key={key}
              dataKey={key}
              fill={chartPalette[index % chartPalette.length]}
              radius={seriesKeys.length === 1 ? [6, 6, 0, 0] : [2, 2, 0, 0]}
              stackId={pivoted ? "total" : undefined}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <ReLineChart data={data}>
        <CartesianGrid stroke="#e7ebef" vertical={false} />
        <XAxis dataKey={xKey} tick={{ fill: "#617080", fontSize: 12 }} tickFormatter={shortTick} />
        <YAxis tick={{ fill: "#617080", fontSize: 12 }} tickFormatter={compactNumber} />
        <Tooltip formatter={(value, name) => [formatValue(value), prettyLabel(name)]} labelFormatter={formatValue} />
        {seriesKeys.length > 1 && <Legend formatter={prettyLabel} />}
        {seriesKeys.map((key, index) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            stroke={chartPalette[index % chartPalette.length]}
            strokeWidth={3}
            dot={{ r: 3 }}
            connectNulls
          />
        ))}
      </ReLineChart>
    </ResponsiveContainer>
  );
}

function pickMetricKey(data, keys, exclude = []) {
  return pickMetricKeys(data, keys, exclude)[0] || keys.find((key) => !exclude.includes(key)) || keys[0];
}

function pickMetricKeys(data, keys, exclude = []) {
  const excluded = new Set(exclude.filter(Boolean));
  return keys.filter((key) => !excluded.has(key) && data.some((row) => isNumericValue(row[key])));
}

function pickDimensionKey(data, keys) {
  const preferred = ["period", "month", "week", "day", "date", "team_member", "assignee", "channel", "status"];
  const preferredKey = keys.find((key) => preferred.some((term) => key.includes(term)) && data.some((row) => !isNumericValue(row[key])));
  if (preferredKey) return preferredKey;
  return keys.find((key) => data.some((row) => !isNumericValue(row[key]))) || keys[0];
}

function pickCategoryKey(data, keys, xKey) {
  const xValues = new Set(data.map((row) => String(row[xKey])));
  if (xValues.size === data.length) return null;
  const preferred = ["channel", "assignee", "team_member", "status", "lifecycle", "current_step"];
  return keys.find((key) => key !== xKey && preferred.some((term) => key.includes(term)) && data.some((row) => !isNumericValue(row[key]))) || null;
}

function pivotSeries(rows, xKey, categoryKey, metricKey) {
  const buckets = new Map();
  const series = [];
  for (const row of rows) {
    const xValue = formatValue(row[xKey]);
    const seriesName = formatValue(row[categoryKey]) || "Unknown";
    if (!series.includes(seriesName)) series.push(seriesName);
    const bucket = buckets.get(xValue) || { [xKey]: xValue };
    bucket[seriesName] = asNumber(row[metricKey]);
    buckets.set(xValue, bucket);
  }
  return {
    data: Array.from(buckets.values()),
    seriesKeys: series.slice(0, 6),
  };
}

function normalizeChartData(rows) {
  return rows.map((row) => {
    const next = { ...row };
    for (const [key, value] of Object.entries(next)) {
      next[key] = isNumericValue(value) ? asNumber(value) : formatValue(value);
    }
    return next;
  });
}

function isNumericValue(value) {
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value !== "string" || value.trim() === "") return false;
  return Number.isFinite(Number(value));
}

function asNumber(value) {
  return typeof value === "number" ? value : Number(value);
}

function prettyLabel(value) {
  return String(value).replaceAll("_", " ");
}

function shortTick(value) {
  const text = formatValue(value);
  return text.length > 14 ? `${text.slice(0, 13)}...` : text;
}

function compactNumber(value) {
  const number = asNumber(value);
  if (!Number.isFinite(number)) return value;
  return Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(number);
}

function formatValue(value) {
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(value ?? "");
}

function EvidencePanel({ answer }) {
  return (
    <aside className="evidence-panel">
      <section>
        <h2>Evidence</h2>
        <ul>
          {(answer.evidence || []).map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      </section>
      <section>
        <h2>SQL</h2>
        {(answer.sql || []).map((item, index) => (
          <details key={`${item.title}-${index}`} open={index === 0}>
            <summary>{item.title}</summary>
            <pre>{item.query}</pre>
          </details>
        ))}
      </section>
    </aside>
  );
}

const seedAnswer = {
  mode: "investigation",
  title: "Investigation diagnosis",
  diagnosis:
    "I will decompose business-level questions into the signals that explain them: trend, channel mix, response pressure, backlog, and client risk. Connect Neon to replace this seeded preview with live analysis.",
  confidence: "Medium",
  caveats: ["Seeded preview only; live answers use Neon and the LLM planner."],
  recommended_actions: ["Ask a business question or open Anomaly Radar to start from live data."],
  plan: [
    {
      title: "New clients by week",
      rationale: "Checks whether new-client intake actually declined and when it started.",
      status: "ready",
    },
    {
      title: "Channel mix",
      rationale: "Looks for whether the decline is concentrated in one acquisition channel.",
      status: "ready",
    },
    {
      title: "Response pressure",
      rationale: "Checks if slower response speed could be hurting conversion.",
      status: "ready",
    },
  ],
  visualizations: [
    {
      type: "line",
      title: "New clients by week",
      data: [
        { period: "May 04", new_clients: 118 },
        { period: "May 11", new_clients: 126 },
        { period: "May 18", new_clients: 110 },
        { period: "May 25", new_clients: 93 },
        { period: "Jun 01", new_clients: 89 },
        { period: "Jun 08", new_clients: 82 },
      ],
    },
    {
      type: "bar",
      title: "Conversation sources",
      data: [
        { channel: "Referral", conversations: 242 },
        { channel: "Website", conversations: 196 },
        { channel: "WhatsApp", conversations: 148 },
        { channel: "Email", conversations: 86 },
      ],
    },
  ],
  evidence: ["Live schema discovery is wired through FastAPI.", "SQL is validated as read-only before execution."],
  sql: [
    {
      title: "Schema discovery",
      query:
        "select table_name\nfrom information_schema.tables\nwhere table_schema = 'public'\norder by table_name\nlimit 500",
    },
  ],
};

function compactHistoryItem(answer) {
  return {
    question: answer.question,
    title: answer.title,
    diagnosis: answer.diagnosis,
  };
}

function loadSavedInvestigations() {
  try {
    const raw = localStorage.getItem(savedStorageKey);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function confidenceCopy(confidence) {
  if (confidence === "High") return "The answer is supported by direct query evidence and clear signal movement.";
  if (confidence === "Low") return "Treat this as directional; the data may be sparse or the current period may be incomplete.";
  return "Useful for decision-making, with caveats worth checking before escalation.";
}

function riskReason(client) {
  const reasons = [];
  if (client.blocked) reasons.push("blocked");
  if (client.is_handed_off) reasons.push("handed off");
  if (client.is_emergency) reasons.push("emergency");
  if (client.ai_active === false || client.ai_eligible === false) reasons.push("AI unavailable");
  if ((client.incoming_messages || 0) > (client.outgoing_messages || 0) + 4) reasons.push("incoming backlog");
  if (!reasons.length) reasons.push("stale or under-covered");
  return reasons.join(", ");
}

function formatDate(value) {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function viewTitle(activeView) {
  if (activeView === "radar") return "Anomaly Radar";
  if (activeView === "risk") return "Client Risk Queue";
  if (activeView === "schema") return "Schema";
  return "Ask";
}

function viewDescription(activeView) {
  if (activeView === "radar") return "Proactive monitoring for unusual movement in conversations, channels, response gaps, and operating friction.";
  if (activeView === "risk") return "A prioritized queue of clients who may need human attention before they churn or stall.";
  if (activeView === "schema") return "A live map of the Postgres tables and columns available to the query planner.";
  return "Ask real business questions against conversation, client, and team signals.";
}

createRoot(document.getElementById("root")).render(<App />);
