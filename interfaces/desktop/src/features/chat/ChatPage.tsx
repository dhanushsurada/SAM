import { useEffect, useRef, useState, useMemo } from "react";
import { FiPlus, FiMessageSquare, FiTrash2, FiSidebar, FiCompass } from "react-icons/fi";
import { Button } from "@/components/Button";
import { ModeBadge } from "@/components/ModeBadge";
import { StatusPill } from "@/components/StatusPill";
import { TERMINAL_PHASES } from "@/api/types";
import type { TaskRecord } from "@/api/types";
import { useTaskSession } from "@/stores/taskSession";
import { phaseLabel, phaseToSamState } from "@/features/iqoo/phase";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { ChatComposer } from "./ChatComposer";
import { useTaskLabel, VoiceStatusLine } from "@/features/voice/VoiceControls";
import { isVoiceTask } from "@/features/voice/taskLabel";
import type { ChatMessage, ChatConversation } from "./types";

const CONVERSATIONS_STORAGE_KEY = "sam.desktop.chat.conversations.v2";
const ACTIVE_CONV_STORAGE_KEY = "sam.desktop.chat.active_conversation.v2";

const STARTER_PROMPTS = [
  { label: "🎵 Play Aya Sher on YouTube", text: "play aya sher song on youtube" },
  { label: "📸 Take screenshot to Desktop", text: "take a screenshot and save it on desktop" },
  { label: "🌐 Open Google Chrome", text: "open Google Chrome" },
  { label: "💡 Who are you?", text: "who are you and what can you do?" },
  { label: "🧮 Calculate 25 * 40", text: "calculate 25 * 40" },
];

function isTerminal(status: string): boolean {
  return TERMINAL_PHASES.has(status as never);
}

function replyFor(task: TaskRecord): ChatMessage | null {
  const base = { id: `${task.task_id}-reply`, role: "assistant" as const, timestamp: task.updated_at };
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
  const {
    sessionTasks,
    selectedTaskId,
    selectTask,
    events,
    submitting,
    submitError,
    submitTask,
    cancelling,
    cancelSelected,
  } = useTaskSession();
  const bottomRef = useRef<HTMLDivElement>(null);
  const labelOf = useTaskLabel();

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

  // Sync conversations to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(CONVERSATIONS_STORAGE_KEY, JSON.stringify(conversations));
      localStorage.setItem(ACTIVE_CONV_STORAGE_KEY, activeConvId);
    } catch {
      // ignore
    }
  }, [conversations, activeConvId]);

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

  // Tasks belonging to the active conversation
  const activeTasks = useMemo(() => {
    if (!activeConv || activeConv.taskIds.length === 0) {
      if (conversations.length === 1 && sessionTasks.length > 0) {
        return sessionTasks;
      }
      return [];
    }
    const taskIdSet = new Set(activeConv.taskIds);
    return sessionTasks.filter((t) => taskIdSet.has(t.task_id));
  }, [activeConv, sessionTasks, conversations.length]);

  const latest = activeTasks.length > 0 ? activeTasks[activeTasks.length - 1] : null;
  const latestId = latest ? latest.task_id : null;
  const running = submitting || (latest !== null && !isTerminal(latest.status));

  useEffect(() => {
    if (latestId && selectedTaskId !== latestId) selectTask(latestId);
  }, [latestId, selectedTaskId, selectTask]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeTasks.length, events.length]);

  const handleCreateNewChat = () => {
    const newId = `conv-${Date.now()}`;
    const newConv: ChatConversation = {
      id: newId,
      title: "New Chat",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      taskIds: [],
    };
    setConversations((prev) => [newConv, ...prev]);
    setActiveConvId(newId);
  };

  const handleDeleteConversation = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (conversations.length <= 1) {
      const newId = `conv-${Date.now()}`;
      setConversations([
        {
          id: newId,
          title: "Main Chat",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          taskIds: [],
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
    const task = await submitTask({ instruction: text, input_type: "text", attachments: [] });
    if (task) {
      setConversations((prev) =>
        prev.map((conv) => {
          if (conv.id === activeConvId) {
            const isFirst = conv.taskIds.length === 0 || conv.title === "New Chat" || conv.title === "Main Chat";
            const newTitle = isFirst ? text.slice(0, 32) + (text.length > 32 ? "…" : "") : conv.title;
            return {
              ...conv,
              title: newTitle,
              updatedAt: new Date().toISOString(),
              taskIds: [...conv.taskIds, task.task_id],
            };
          }
          return conv;
        })
      );
    }
  };

  const lastEvent = events.length > 0 ? events[events.length - 1] : undefined;

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

          <Button variant="ghost" size="sm" onClick={handleCreateNewChat}>
            <FiPlus size={14} /> New Chat
          </Button>
        </div>

        {/* Message Thread */}
        <div className="flex-1 space-y-3 overflow-y-auto pr-1">
          {activeTasks.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center p-6 space-y-4">
              <div className="p-3 bg-surface border border-line rounded-full text-ember">
                <FiCompass size={28} />
              </div>
              <div>
                <h3 className="text-base font-medium text-ink">What can SAM do for you?</h3>
                <p className="text-xs text-mute mt-1 max-w-md">
                  SAM executes actions directly on this computer: launch and close apps, play music, search the web, take screenshots, or answer questions.
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

          {activeTasks.map((task) => {
            const reply = replyFor(task);
            const isLive = task.task_id === selectedTaskId;
            const phase = isLive && lastEvent ? lastEvent.phase : task.status;
            return (
              <div key={task.task_id} className="space-y-3">
                <ChatMessageBubble
                  message={{
                    id: task.task_id,
                    role: "user",
                    content: labelOf(task),
                    timestamp: task.created_at,
                    via: isVoiceTask(task) ? "voice" : undefined,
                  }}
                />
                {reply ? (
                  <ChatMessageBubble message={reply} />
                ) : (
                  <div className="flex justify-start">
                    <StatusPill
                      state={phaseToSamState(phase)}
                      label={(isLive && lastEvent ? lastEvent.message : null) ?? phaseLabel(phase)}
                      live={isLive}
                    />
                  </div>
                )}
              </div>
            );
          })}
          <div ref={bottomRef} />
        </div>

        {/* Footer / Composer */}
        {submitError && <p className="pt-2 text-xs text-danger">{submitError}</p>}
        {running && !submitting && (
          <div className="flex justify-end pt-2">
            <Button variant="ghost" size="sm" onClick={cancelSelected} loading={cancelling}>
              Cancel this task
            </Button>
          </div>
        )}
        <div className="pt-3">
          <ChatComposer onSend={handleSend} disabled={running} />
          <div className="px-1 pt-2">
            <VoiceStatusLine showUnavailable />
          </div>
        </div>
      </div>
    </div>
  );
}
