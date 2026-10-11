"use client";
import React, { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Database, Activity, RefreshCw, Plus, Pencil, Trash2, Eye, Loader2,
  CheckCircle2, XCircle, Clock, Mic,
} from "lucide-react";
import { useRouter } from "next/navigation";
import Navbar from "@/components/Navbar";
import AgentWizard from "@/components/AgentWizard";

import { API_URL, apiFetch, authToken } from "@/lib/api";

function EmptyState({ title, text }) {
  return (
    <div className="text-center py-10">
      <p className="text-sm text-white/80 font-medium">{title}</p>
      <p className="text-xs text-muted mt-2">{text}</p>
    </div>
  );
}

function IconBtn({ title, onClick, children, tone = "default", disabled = false }) {
  const toneClass = tone === "danger"
    ? "text-muted hover:text-red-400 hover:bg-red-400/10"
    : "text-muted hover:text-saffron hover:bg-saffron/10";

  return (
    <button
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={`w-8 h-8 rounded-full bg-white/5 flex items-center justify-center transition-all disabled:opacity-40 ${toneClass}`}
    >
      {children}
    </button>
  );
}

function SessionEditorModal({ open, session, onClose, onSave }) {
  const [status, setStatus] = useState("active");
  const [isComplete, setIsComplete] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!session) return;
    setStatus(session.status || "active");
    setIsComplete(Boolean(session.is_complete));
  }, [session]);

  const handleSave = async () => {
    if (!session) return;
    setSaving(true);
    await onSave(session.id, { status, is_complete: isComplete });
    setSaving(false);
    onClose();
  };

  if (!open || !session) return null;

  return (
    <div className="fixed inset-0 z-[70] bg-black/70 backdrop-blur-sm flex items-center justify-center p-6">
      <div className="w-full max-w-md bg-[#0e0e0e] border border-white/10 rounded-3xl p-6">
        <h3 className="text-xl font-display text-white mb-1">Edit Live Session</h3>
        <p className="text-xs text-muted font-mono mb-6">{session.id}</p>

        <div className="space-y-4">
          <div>
            <label className="text-[10px] font-mono text-muted uppercase tracking-widest block mb-2">
              Status
            </label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-saffron/50"
            >
              <option className="bg-[#121212]" value="active">active</option>
              <option className="bg-[#121212]" value="completed">completed</option>
              <option className="bg-[#121212]" value="paused">paused</option>
            </select>
          </div>

          <label className="flex items-center gap-3 text-sm text-white">
            <input
              type="checkbox"
              checked={isComplete}
              onChange={(e) => setIsComplete(e.target.checked)}
              className="accent-saffron"
            />
            Mark as complete
          </label>
        </div>

        <div className="flex justify-end gap-3 mt-8">
          <button
            onClick={onClose}
            className="px-5 py-2.5 rounded-full border border-white/10 text-sm hover:bg-white/5 transition-all"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="btn-primary px-5 py-2.5 rounded-full text-sm disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

function SessionCreateModal({ open, agents, onClose, onCreate }) {
  const [agentId, setAgentId] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (agents.length > 0) setAgentId(agents[0].id);
  }, [agents]);

  const create = async () => {
    if (!agentId) return;
    setCreating(true);
    await onCreate(agentId);
    setCreating(false);
    onClose();
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] bg-black/70 backdrop-blur-sm flex items-center justify-center p-6">
      <div className="w-full max-w-md bg-[#0e0e0e] border border-white/10 rounded-3xl p-6">
        <h3 className="text-xl font-display text-white mb-1">Create Live Session</h3>
        <p className="text-xs text-muted font-mono mb-6">Select base agent template</p>

        <select
          value={agentId}
          onChange={(e) => setAgentId(e.target.value)}
          className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-saffron/50"
        >
          {agents.map((a) => (
            <option key={a.id} className="bg-[#121212]" value={a.id}>
              {a.name} ({a.domain})
            </option>
          ))}
        </select>

        <div className="flex justify-end gap-3 mt-8">
          <button
            onClick={onClose}
            className="px-5 py-2.5 rounded-full border border-white/10 text-sm hover:bg-white/5 transition-all"
          >
            Cancel
          </button>
          <button
            onClick={create}
            disabled={!agentId || creating}
            className="btn-primary px-5 py-2.5 rounded-full text-sm disabled:opacity-50"
          >
            {creating ? "Creating..." : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AnalysisPage() {
  const router = useRouter();

  const [agents, setAgents] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [showAgentWizard, setShowAgentWizard] = useState(false);
  const [editingAgent, setEditingAgent] = useState(null);

  const [showSessionEditor, setShowSessionEditor] = useState(false);
  const [editingSession, setEditingSession] = useState(null);

  const [showSessionCreator, setShowSessionCreator] = useState(false);

  const activeSessions = useMemo(
    () => sessions.filter((s) => s.status === "active").length,
    [sessions]
  );
  const completedSessions = useMemo(
    () => sessions.filter((s) => s.status === "completed").length,
    [sessions]
  );

  const fetchAll = async () => {
    setLoading(true);
    setError("");
    try {
      const [agentRes, sessionRes] = await Promise.all([
        apiFetch(`/agents`),
        apiFetch(`/sessions`),
      ]);

      if (!agentRes.ok || !sessionRes.ok) {
        throw new Error("Failed to fetch dashboard data from backend.");
      }

      const agentData = await agentRes.json();
      const sessionData = await sessionRes.json();

      setAgents(agentData.agents || []);
      setSessions(sessionData.sessions || []);
    } catch (err) {
      setError(err.message || "Unknown error while loading data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
  }, []);

  const handleSaveAgent = async (agentData) => {
    setBusy(true);
    try {
      if (editingAgent?.id) {
        const res = await apiFetch(`/agents/${editingAgent.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(agentData),
        });
        if (!res.ok) throw new Error("Failed to update agent.");
      } else {
        const res = await apiFetch(`/agents`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(agentData),
        });
        if (!res.ok) throw new Error("Failed to create agent.");
      }
      await fetchAll();
      setShowAgentWizard(false);
      setEditingAgent(null);
    } catch (err) {
      setError(err.message || "Agent save failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteAgent = async (agentId) => {
    if (!window.confirm("Delete this agent? Sessions under this agent may be affected.")) return;
    setBusy(true);
    try {
      const res = await apiFetch(`/agents/${agentId}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Failed to delete agent.");
      await fetchAll();
    } catch (err) {
      setError(err.message || "Agent delete failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleCreateSession = async (agentId) => {
    setBusy(true);
    try {
      const res = await apiFetch(`/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: agentId }),
      });
      if (!res.ok) throw new Error("Failed to create session.");
      await fetchAll();
    } catch (err) {
      setError(err.message || "Session create failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleUpdateSession = async (sessionId, payload) => {
    setBusy(true);
    try {
      const res = await apiFetch(`/sessions/${sessionId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Failed to update session.");
      await fetchAll();
    } catch (err) {
      setError(err.message || "Session update failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteSession = async (sessionId) => {
    if (!window.confirm("Delete this session and its messages?")) return;
    setBusy(true);
    try {
      const res = await apiFetch(`/sessions/${sessionId}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Failed to delete session.");
      await fetchAll();
    } catch (err) {
      setError(err.message || "Session delete failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <div className="noise-overlay" />

      <main className="pt-28 pb-24 px-6 max-w-7xl mx-auto relative z-10 space-y-8">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h1 className="text-4xl md:text-5xl font-display text-white mb-2">
              Analysis <span className="italic opacity-60">— Data Operations</span>
            </h1>
            <p className="text-muted text-sm max-w-3xl">
              Unified operational view for Agent definitions and Live Interaction sessions with in-place CRUD actions.
            </p>
          </div>

          <button
            onClick={fetchAll}
            disabled={loading || busy}
            className="px-5 py-3 rounded-full border border-white/10 text-sm hover:bg-white/5 transition-all flex items-center gap-2 disabled:opacity-40"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-2xl p-4 text-red-300 text-sm">
            {error}
          </div>
        )}

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-white/[0.03] border border-white/10 rounded-2xl p-5">
            <p className="text-[10px] font-mono text-muted uppercase tracking-widest mb-1">Agents</p>
            <p className="text-3xl font-display text-saffron">{agents.length}</p>
          </div>
          <div className="bg-white/[0.03] border border-white/10 rounded-2xl p-5">
            <p className="text-[10px] font-mono text-muted uppercase tracking-widest mb-1">Live Sessions</p>
            <p className="text-3xl font-display text-cyan-vivid">{sessions.length}</p>
          </div>
          <div className="bg-white/[0.03] border border-white/10 rounded-2xl p-5">
            <p className="text-[10px] font-mono text-muted uppercase tracking-widest mb-1">Active</p>
            <p className="text-3xl font-display text-emerald-500">{activeSessions}</p>
          </div>
          <div className="bg-white/[0.03] border border-white/10 rounded-2xl p-5">
            <p className="text-[10px] font-mono text-muted uppercase tracking-widest mb-1">Completed</p>
            <p className="text-3xl font-display text-white">{completedSessions}</p>
          </div>
        </div>

        <div className="grid xl:grid-cols-2 gap-8">
          <motion.section
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-white/[0.02] border border-white/10 rounded-3xl p-6"
          >
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-saffron/10 border border-saffron/20 flex items-center justify-center">
                  <Database size={16} className="text-saffron" />
                </div>
                <div>
                  <h2 className="text-xl font-display text-white">Agents Database</h2>
                  <p className="text-[10px] font-mono text-muted uppercase tracking-widest">Create / Read / Update / Delete</p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <IconBtn
                  title="Live capture (record & summarise a conversation)"
                  onClick={async () => {
                    // Open synchronously (popup blockers), then point it at the page once the token is ready
                    const tab = window.open("", "_blank");
                    if (!tab) return;
                    tab.opener = null;
                    tab.location.href = `${API_URL}/live#token=${encodeURIComponent(await authToken())}`;
                  }}
                >
                  <Mic size={14} />
                </IconBtn>
                <IconBtn
                  title="Create Agent"
                  onClick={() => {
                    setEditingAgent(null);
                    setShowAgentWizard(true);
                  }}
                >
                  <Plus size={14} />
                </IconBtn>
              </div>
            </div>

            {loading ? (
              <div className="py-10 flex justify-center"><Loader2 size={24} className="animate-spin text-saffron" /></div>
            ) : agents.length === 0 ? (
              <EmptyState title="No agents found" text="Create an agent from the + icon." />
            ) : (
              <div className="space-y-3 max-h-[28rem] overflow-y-auto pr-1">
                {agents.map((agent) => (
                  <div key={agent.id} className="bg-white/[0.02] border border-white/8 rounded-2xl p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-white text-sm font-medium">{agent.name}</p>
                        <p className="text-[10px] text-muted font-mono mt-1">
                          {agent.id} • {agent.domain}
                        </p>
                        <p className="text-[10px] text-muted mt-2">
                          Fields: {(agent.fields || []).length} • Inputs: {(agent.inputs || []).join(", ")}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <IconBtn title="Read / Open Session" onClick={() => router.push(`/session/${agent.id}`)}>
                          <Eye size={14} />
                        </IconBtn>
                        <IconBtn title="Update Agent" onClick={() => { setEditingAgent(agent); setShowAgentWizard(true); }}>
                          <Pencil size={14} />
                        </IconBtn>
                        <IconBtn title="Delete Agent" tone="danger" onClick={() => handleDeleteAgent(agent.id)}>
                          <Trash2 size={14} />
                        </IconBtn>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </motion.section>

          <motion.section
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08 }}
            className="bg-white/[0.02] border border-white/10 rounded-3xl p-6"
          >
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-cyan-vivid/10 border border-cyan-vivid/20 flex items-center justify-center">
                  <Activity size={16} className="text-cyan-vivid" />
                </div>
                <div>
                  <h2 className="text-xl font-display text-white">Live Interaction Sessions</h2>
                  <p className="text-[10px] font-mono text-muted uppercase tracking-widest">Create / Read / Update / Delete</p>
                </div>
              </div>

              <IconBtn title="Create Session" onClick={() => setShowSessionCreator(true)} disabled={agents.length === 0}>
                <Plus size={14} />
              </IconBtn>
            </div>

            {loading ? (
              <div className="py-10 flex justify-center"><Loader2 size={24} className="animate-spin text-saffron" /></div>
            ) : sessions.length === 0 ? (
              <EmptyState title="No sessions found" text="Create a live session from the + icon." />
            ) : (
              <div className="space-y-3 max-h-[28rem] overflow-y-auto pr-1">
                {sessions.map((session) => (
                  <div key={session.id} className="bg-white/[0.02] border border-white/8 rounded-2xl p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-white text-sm font-medium">{session.agent_name}</p>
                        <p className="text-[10px] text-muted font-mono mt-1">
                          {session.id} • {session.agent_domain}
                        </p>
                        <div className="flex items-center gap-3 mt-2 text-[10px] font-mono">
                          <span className="text-muted inline-flex items-center gap-1">
                            <Clock size={11} /> {session.turn_count || 0} turns
                          </span>
                          <span className="text-muted">
                            {session.message_count || 0} messages
                          </span>
                          <span className={`inline-flex items-center gap-1 ${
                            session.is_complete ? "text-emerald-500" : "text-saffron"
                          }`}>
                            {session.is_complete ? <CheckCircle2 size={11} /> : <XCircle size={11} />}
                            {session.is_complete ? "complete" : "incomplete"}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <IconBtn
                          title="Read / View Stats"
                          onClick={() => router.push(`/session/${session.agent_id}/stats?sid=${session.id}`)}
                        >
                          <Eye size={14} />
                        </IconBtn>
                        <IconBtn
                          title="Update Session"
                          onClick={() => {
                            setEditingSession(session);
                            setShowSessionEditor(true);
                          }}
                        >
                          <Pencil size={14} />
                        </IconBtn>
                        <IconBtn
                          title="Delete Session"
                          tone="danger"
                          onClick={() => handleDeleteSession(session.id)}
                        >
                          <Trash2 size={14} />
                        </IconBtn>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </motion.section>
        </div>
      </main>

      <AnimatePresence>
        {showAgentWizard && (
          <AgentWizard
            onClose={() => {
              setShowAgentWizard(false);
              setEditingAgent(null);
            }}
            onSave={handleSaveAgent}
            initialData={editingAgent}
          />
        )}
      </AnimatePresence>

      <SessionEditorModal
        open={showSessionEditor}
        session={editingSession}
        onClose={() => {
          setShowSessionEditor(false);
          setEditingSession(null);
        }}
        onSave={handleUpdateSession}
      />

      <SessionCreateModal
        open={showSessionCreator}
        agents={agents}
        onClose={() => setShowSessionCreator(false)}
        onCreate={handleCreateSession}
      />
    </div>
  );
}
