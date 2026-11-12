import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { FiPlus, FiMessageSquare, FiTrash2, FiSidebar, FiCompass, FiFolder, FiX } from "react-icons/fi";
import { Link } from "react-router-dom";
import { Button } from "@/components/Button";
import { ModeBadge } from "@/components/ModeBadge";
import type { TaskRecord } from "@/api/types";
import {
  sendChatMessage,
  listChatConversations,
  getConversationMessages,
  deleteChatConversation,
  listProjects,
  type ProjectItem,
} from "@/api/client";
import { useTaskSession } from "@/stores/taskSession";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { ChatComposer } from "./ChatComposer";
import { useTaskLabel, VoiceStatusLine } from "@/features/voice/VoiceControls";
import { isVoiceTask } from "@/features/voice/taskLabel";
import type { ChatMessage, ChatConversation } from "./types";

const CONVERSATIONS_STORAGE_KEY = "sam.desktop.chat.conversations.v3";
const ACTIVE_CONV_STORAGE_KEY = "sam.desktop.chat.active_conversation.v3";

const STARTER_PROMPTS = [
  { label: "💡 Who are you?", text: "who are you and what can you do?" },
  { label: "⚡ How do I run fast with Groq / Cloud?", text: "how do I add a Groq or Gemini API key for instant responses?" },
  { label: "🔌 What plugins & MCP are available?", text: "what MCP plugins and integrations can I connect?" },
  { label: "🧠 How does Founder Mode work?", text: "how does founder mode learn my preferences?" },
  { label: "💻 Help me write a script", text: "write a python script to monitor folder changes and log files" },
];

function replyFor(task: TaskRecord): ChatMessage | null {
  const base = {
    id: `${task.task_id}-reply`,
    role: "assistant" as const,
    timestamp: task.updated_at,
    taskId: task.task_id,
  };
  if (task.status === "completed") {
    return { ...base, content: task.result_text || "Done.", tone: "default" };
  }
  if (task.status === "failed") {
    return { ...base, content: task.error || task.result_text || "That didn't complete.", tone: "danger" };
  }
  if (task.status === "cancelled") {
    return { ...base, content: "Cancelled.", tone: "muted" };
  }
  return null;
}

export function ChatPage() {
  const { sessionTasks } = useTaskSession();
  const bottomRef = useRef<HTMLDivElement>(null);
  const labelOf = useTaskLabel();
  const [isChatThinking, setIsChatThinking] = useState(false);

  // Projects Context
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [activeProject, setActiveProject] = useState<ProjectItem | null>(() => {
    try {
      const raw = localStorage.getItem("sam.desktop.active_project");
      if (raw) return JSON.parse(raw);
    } catch {
      // ignore
    }
    return null;
  });

  // ─── Multiple Parallel Conversations State ─────────────────────────────
  const [conversations, setConversations] = useState<ChatConversation[]>(() => {
    try {
      const raw = localStorage.getItem(CONVERSATIONS_STORAGE_KEY);
      if (raw) return JSON.parse(raw);
    } catch {
      // ignore
    }
    const initialId = `conv-${Date.now()}`;
    return [
      {
        id: initialId,
        title: "Main Chat",
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        taskIds: [],
        messages: [],
      },
    ];
  });

  const [activeConvId, setActiveConvId] = useState<string>(() => {
    try {
      const saved = localStorage.getItem(ACTIVE_CONV_STORAGE_KEY);
      if (saved) return saved;
    } catch {
      // ignore
    }
    return conversations[0]?.id || `conv-${Date.now()}`;
  });

  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Load projects from backend
  useEffect(() => {
    void listProjects().then((res) => {
      setProjects(res.projects || []);
    }).catch(() => {});
  }, []);

  // Fetch persistent conversations from backend SQLite on mount
  const loadBackendConversations = useCallback(async () => {
    try {
      const res = await listChatConversations(activeProject?.id);
      if (res.conversations && res.conversations.length > 0) {
        setConversations((prev) => {
          const map = new Map(prev.map((c) => [c.id, c]));
          const merged: ChatConversation[] = res.conversations.map((bc) => {
            const existing = map.get(bc.id);
            return {
              id: bc.id,
              title: bc.title || "Chat",
              createdAt: bc.created_at,
              updatedAt: bc.updated_at,
              taskIds: existing?.taskIds || [],
              messages: existing?.messages || [],
            };
          });
          return merged.length > 0 ? merged : prev;
        });
      }
    } catch {
      // ignore offline
    }
  }, [activeProject?.id]);

  useEffect(() => {
    void loadBackendConversations();
  }, [loadBackendConversations]);

  // Load messages from SQLite if current conversation has empty messages
  useEffect(() => {
    const current = conversations.find((c) => c.id === activeConvId);
    if (current && (!current.messages || current.messages.length === 0)) {
      void getConversationMessages(activeConvId).then((res) => {
        if (res.messages && res.messages.length > 0) {
          const loadedMsgs: ChatMessage[] = res.messages.map((m) => ({
            id: m.id,
            role: m.role === "assistant" ? "assistant" : "user",
            content: m.content,
            timestamp: m.timestamp,
            tone: (m.tone as "default" | "danger" | "muted") || "default",
          }));
          setConversations((prev) =>
            prev.map((conv) => (conv.id === activeConvId ? { ...conv, messages: loadedMsgs } : conv))
          );
        }
      }).catch(() => {});
    }
  }, [activeConvId, conversations]);

  // Sync conversations to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(CONVERSATIONS_STORAGE_KEY, JSON.stringify(conversations));
      localStorage.setItem(ACTIVE_CONV_STORAGE_KEY, activeConvId);
    } catch {
      // ignore
    }
  }, [conversations, activeConvId]);

  // Sync active project to localStorage
  useEffect(() => {
    try {
      if (activeProject) {
        localStorage.setItem("sam.desktop.active_project", JSON.stringify(activeProject));
      } else {
        localStorage.removeItem("sam.desktop.active_project");
      }
    } catch {
      // ignore
    }
  }, [activeProject]);

  // Ensure active conversation exists
  useEffect(() => {
    if (!conversations.some((c) => c.id === activeConvId)) {
      if (conversations.length > 0) {
        setActiveConvId(conversations[0].id);
      } else {
        const newId = `conv-${Date.now()}`;
        const newConv: ChatConversation = {
          id: newId,
          title: "New Chat",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          taskIds: [],
          messages: [],
        };
        setConversations([newConv]);
        setActiveConvId(newId);
      }
    }
  }, [conversations, activeConvId]);

  const activeConv = useMemo(
    () => conversations.find((c) => c.id === activeConvId) ?? conversations[0],
    [conversations, activeConvId]
  );

  // Tasks belonging to the active conversation (legacy task fallback)
  const activeTasks = useMemo(() => {
    if (!activeConv || activeConv.taskIds.length === 0) {
      return [];
    }
    const taskIdSet = new Set(activeConv.taskIds);
    return sessionTasks.filter((t) => taskIdSet.has(t.task_id));
  }, [activeConv, sessionTasks]);

  const currentMessages: ChatMessage[] = useMemo(() => {
    if (activeConv?.messages && activeConv.messages.length > 0) {
      return activeConv.messages;
    }
    if (activeTasks.length > 0) {
      const msgs: ChatMessage[] = [];
      for (const t of activeTasks) {
        msgs.push({
          id: t.task_id,
          role: "user",
          content: labelOf(t),
          timestamp: t.created_at,
          via: isVoiceTask(t) ? "voice" : undefined,
        });
        const rep = replyFor(t);
        if (rep) msgs.push(rep);
      }
      return msgs;
    }
    return [];
  }, [activeConv, activeTasks, labelOf]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [currentMessages.length, isChatThinking]);

  const handleCreateNewChat = () => {
    const newId = `conv-${Date.now()}`;
    const newConv: ChatConversation = {
      id: newId,
      title: "New Chat",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      taskIds: [],
      messages: [],
    };
    setConversations((prev) => [newConv, ...prev]);
    setActiveConvId(newId);
  };

  const handleDeleteConversation = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    void deleteChatConversation(id).catch(() => {});
    if (conversations.length <= 1) {
      const newId = `conv-${Date.now()}`;
      setConversations([
        {
          id: newId,
          title: "Main Chat",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          taskIds: [],
          messages: [],
        },
      ]);
      setActiveConvId(newId);
      return;
    }
    const remaining = conversations.filter((c) => c.id !== id);
    setConversations(remaining);
    if (activeConvId === id) {
      setActiveConvId(remaining[0].id);
    }
  };

  const handleSend = async (text: string) => {
    if (!text.trim() || isChatThinking) return;

    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}-user`,
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };

    setConversations((prev) =>
      prev.map((conv) => {
        if (conv.id === activeConvId) {
          const prevMsgs = conv.messages || [];
          const isFirst = prevMsgs.length === 0 || conv.title === "New Chat" || conv.title === "Main Chat";
          const newTitle = isFirst ? text.slice(0, 32) + (text.length > 32 ? "…" : "") : conv.title;
          return {
            ...conv,
            title: newTitle,
            updatedAt: new Date().toISOString(),
            messages: [...prevMsgs, userMsg],
          };
        }
        return conv;
      })
    );

    setIsChatThinking(true);

    try {
      const active = conversations.find((c) => c.id === activeConvId);
      const history = (active?.messages || []).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      // Call dedicated pure conversational chat endpoint with persistent memory & project context
      const res = await sendChatMessage(
        text,
        activeConvId,
        history,
        activeProject?.id,
        activeProject?.context
      );

      const assistantMsg: ChatMessage = {
        id: `msg-${Date.now()}-assistant`,
        role: "assistant",
        content: res.reply || "Done.",
        timestamp: new Date().toISOString(),
      };

      setConversations((prev) =>
        prev.map((conv) => {
          if (conv.id === activeConvId) {
            return {
              ...conv,
              updatedAt: new Date().toISOString(),
              messages: [...(conv.messages || []), assistantMsg],
            };
          }
          return conv;
        })
      );
    } catch (e: unknown) {
      const errMsg: ChatMessage = {
        id: `msg-${Date.now()}-err`,
        role: "assistant",
        content: e instanceof Error ? e.message : "Error connecting to Brain.",
        timestamp: new Date().toISOString(),
        tone: "danger",
      };
      setConversations((prev) =>
        prev.map((conv) => {
          if (conv.id === activeConvId) {
            return {
              ...conv,
              messages: [...(conv.messages || []), errMsg],
            };
          }
          return conv;
        })
      );
    } finally {
      setIsChatThinking(false);
    }
  };

  return (
    <div className="flex h-full gap-4">
      {/* ─── Conversations Sidebar (Parallel Chats) ───────────────────────── */}
      {sidebarOpen && (
        <aside className="flex w-60 flex-col rounded-lg border border-line bg-surface p-3 text-sm">
          <div className="flex items-center justify-between pb-3 border-b border-line">
            <span className="font-semibold text-ink flex items-center gap-1.5">
              <FiMessageSquare size={16} className="text-ember" /> Chats
            </span>
            <Button variant="secondary" size="sm" onClick={handleCreateNewChat} title="New Chat">
              <FiPlus size={14} /> New
            </Button>
          </div>

          <div className="flex-1 space-y-1.5 overflow-y-auto py-2">
            {conversations.map((conv) => {
              const isActive = conv.id === activeConvId;
              return (
                <div
                  key={conv.id}
                  onClick={() => setActiveConvId(conv.id)}
                  className={`group flex items-center justify-between rounded-md px-2.5 py-2 cursor-pointer transition-colors ${
                    isActive ? "bg-void border border-ember/40 text-ink font-medium" : "hover:bg-void/60 text-mute hover:text-ink"
                  }`}
                >
                  <div className="flex items-center gap-2 truncate">
                    <FiMessageSquare size={13} className={isActive ? "text-ember shrink-0" : "shrink-0"} />
                    <span className="truncate text-xs">{conv.title || "Untitled Chat"}</span>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => handleDeleteConversation(conv.id, e)}
                    className="opacity-0 group-hover:opacity-100 p-1 text-mute hover:text-danger transition-opacity"
                    title="Delete Chat"
                  >
                    <FiTrash2 size={12} />
                  </button>
                </div>
              );
            })}
          </div>
        </aside>
      )}

      {/* ─── Main Chat Window ────────────────────────────────────────────── */}
      <div className="flex flex-1 flex-col h-full max-w-3xl mx-auto">
        {/* Chat Header */}
        <div className="flex items-center justify-between pb-2 border-b border-line mb-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSidebarOpen((v) => !v)}
              className="p-1.5 text-mute hover:text-ink rounded-md hover:bg-surface transition-colors"
              title="Toggle Chats Sidebar"
            >
              <FiSidebar size={16} />
            </button>
            <h1 className="text-base font-semibold text-ink truncate max-w-sm">
              {activeConv?.title || "Chat"}
            </h1>
            <ModeBadge mode="live" />
          </div>

          <div className="flex items-center gap-2">
            {/* Project Context Selector */}
            {activeProject ? (
              <div className="flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs text-amber-300">
                <FiFolder size={12} />
                <span className="truncate max-w-[130px] font-medium">{activeProject.name}</span>
                <button
                  type="button"
                  onClick={() => setActiveProject(null)}
                  className="hover:text-amber-100 ml-0.5"
                  title="Clear project context"
                >
                  <FiX size={12} />
                </button>
              </div>
            ) : projects.length > 0 ? (
              <select
                className="rounded border border-line bg-surface px-2 py-1 text-xs text-mute hover:text-ink focus:outline-none"
                value=""
                onChange={(e) => {
                  const p = projects.find((item) => item.id === e.target.value);
                  if (p) setActiveProject(p);
                }}
              >
                <option value="" disabled>Bind to Project Context...</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            ) : null}

            <Button variant="ghost" size="sm" onClick={handleCreateNewChat}>
              <FiPlus size={14} /> New Chat
            </Button>
          </div>
        </div>

        {/* Message Thread */}
        <div className="flex-1 space-y-3 overflow-y-auto pr-1">
          {currentMessages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center p-6 space-y-4">
              <div className="p-3 bg-surface border border-line rounded-full text-ember">
                <FiCompass size={28} />
              </div>
              <div>
                <h3 className="text-base font-medium text-ink">Conversational Chat with SAM</h3>
                <p className="text-xs text-mute mt-1 max-w-md">
                  Ask questions, discuss topics, write code, or explore ideas. Instant conversational replies with persistent memory across restarts.
                </p>
              </div>

              {/* Starter pills */}
              <div className="flex flex-wrap gap-2 justify-center max-w-lg pt-2">
                {STARTER_PROMPTS.map((starter) => (
                  <button
                    key={starter.text}
                    type="button"
                    onClick={() => void handleSend(starter.text)}
                    className="rounded-full border border-line bg-surface hover:border-ember/60 px-3 py-1.5 text-xs text-ink hover:text-ember transition-colors shadow-sm"
                  >
                    {starter.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {currentMessages.map((msg) => (
            <ChatMessageBubble key={msg.id} message={msg} />
          ))}

          {isChatThinking && (
            <div className="flex items-center gap-2 px-3 py-2 text-xs text-mute border border-line bg-surface rounded-lg max-w-[170px]">
              <span className="w-2 h-2 rounded-full bg-ember animate-ping" />
              <span>SAM is replying…</span>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Footer / Composer */}
        <div className="pt-3 space-y-2">
          <ChatComposer onSend={handleSend} disabled={isChatThinking} />
          <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-[11px] text-mute">
            <div className="flex items-center gap-1.5">
              <span>💬 Fast conversational mode.</span>
              <span>To execute computer tasks, switch to <Link to="/tasks" className="text-ember hover:underline font-medium">Tasks</Link> or <Link to="/" className="text-ember hover:underline font-medium">Command Center</Link>.</span>
            </div>
            <VoiceStatusLine showUnavailable />
          </div>
        </div>
      </div>
    </div>
  );
}
