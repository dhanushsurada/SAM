import { useState, useEffect, useCallback, useMemo } from "react";
import {
  FiZap,
  FiCheckCircle,
  FiPlus,
  FiFolder,
  FiRefreshCw,
  FiPlay,
  FiToggleLeft,
  FiToggleRight,
  FiTrash2,
  FiSearch,
  FiCode,
  FiLayers,
  FiTerminal,
  FiFileText,
  FiShield,
} from "react-icons/fi";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/StatusPill";
import { Card } from "@/components/Card";
import { Button } from "@/components/Button";
import {
  listSkills,
  scanAndInstallSkills,
  openSkillsFolder,
  createCustomSkill,
  toggleSkill,
  deleteCustomSkill,
  executeSkill,
  type SkillItem,
} from "@/api/client";

const DEFAULT_BUILTIN_SKILLS: SkillItem[] = [
  {
    id: "builtin.desktop.control.click",
    name: "desktop.control.click",
    title: "Desktop Visual Clicker",
    description: "Finds UI elements via vision model and performs verified clicks with screen comparison.",
    category: "builtin",
    compiled: true,
    enabled: true,
    execution_type: "builtin",
    triggers: ["click", "press button", "tap on screen"],
    use_count: 14,
    last_used: new Date().toISOString(),
  },
  {
    id: "builtin.desktop.browser.navigate",
    name: "desktop.browser.navigate",
    title: "Autonomous Browser Navigator",
    description: "Launches browser sessions, navigates to target URLs, searches queries, and extracts page content.",
    category: "builtin",
    compiled: true,
    enabled: true,
    execution_type: "builtin",
    triggers: ["open browser", "go to", "browse to"],
    use_count: 28,
    last_used: new Date().toISOString(),
  },
  {
    id: "builtin.desktop.terminal.execute",
    name: "desktop.terminal.execute",
    title: "Sandboxed Terminal Runner",
    description: "Sandboxed terminal process runner with exit-code verification and output capture.",
    category: "builtin",
    compiled: true,
    enabled: true,
    execution_type: "builtin",
    triggers: ["run command", "terminal", "execute bash"],
    use_count: 42,
    last_used: new Date().toISOString(),
  },
  {
    id: "builtin.desktop.vision.inspect",
    name: "desktop.vision.inspect",
    title: "Multimodal Screen Inspector",
    description: "Multimodal screenshot analysis with Moondream for visual element coordinate detection.",
    category: "builtin",
    compiled: true,
    enabled: true,
    execution_type: "builtin",
    triggers: ["look at screen", "inspect display"],
    use_count: 36,
    last_used: new Date().toISOString(),
  },
];

const CATEGORIES = [
  { id: "all", label: "All Skills" },
  { id: "superpowers", label: "Superpowers (15)" },
  { id: "anthropic-agent", label: "Anthropic Skills (21)" },
  { id: "connect-apps", label: "Connect & Apps" },
  { id: "linkedin", label: "LinkedIn Agent" },
  { id: "marketing", label: "Marketing & Growth" },
  { id: "reverse-engineering", label: "Reverse Engineering" },
  { id: "plugins", label: "App Plugins (820)" },
  { id: "custom", label: "Custom Skills" },
];

export function SkillsPage() {
  const [skills, setSkills] = useState<SkillItem[]>(DEFAULT_BUILTIN_SKILLS);
  const [loading, setLoading] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusNotice, setStatusNotice] = useState<string | null>(null);

  // Modals & execution states
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [activeDetailSkill, setActiveDetailSkill] = useState<SkillItem | null>(null);
  const [testExecutionResult, setTestExecutionResult] = useState<{
    skillName: string;
    ok: boolean;
    stdout?: string;
    stderr?: string;
    message?: string;
    guidance_preview?: string;
  } | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [isScanning, setIsScanning] = useState(false);

  // Form state for creating custom skill
  const [customName, setCustomName] = useState("");
  const [customTitle, setCustomTitle] = useState("");
  const [customDescription, setCustomDescription] = useState("");
  const [customCategory, setCustomCategory] = useState("custom");
  const [customTriggers, setCustomTriggers] = useState("");
  const [customExecType, setCustomExecType] = useState("system_command");
  const [customCommand, setCustomCommand] = useState("");
  const [customContent, setCustomContent] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  const fetchSkills = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listSkills();
      if (res.skills && res.skills.length > 0) {
        setSkills(res.skills);
      } else {
        setSkills(DEFAULT_BUILTIN_SKILLS);
      }
    } catch {
      // Keep defaults if fetch fails
      setSkills(DEFAULT_BUILTIN_SKILLS);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchSkills();
  }, [fetchSkills]);

  const showNotice = (msg: string) => {
    setStatusNotice(msg);
    setTimeout(() => setStatusNotice(null), 6000);
  };

  const handleScanAndInstall = async () => {
    setIsScanning(true);
    try {
      const res = await scanAndInstallSkills("plugins");
      if (res.ok) {
        showNotice(
          `Successfully installed ${res.total_installed} skills! (${res.by_category?.superpowers || 15} Superpowers, ${res.by_category?.["anthropic-agent"] || 19} Anthropic Agent skills)`
        );
        await fetchSkills();
      } else {
        showNotice(`Scan completed: ${res.error || "No new skills found"}`);
      }
    } catch (e: unknown) {
      showNotice(`Scan failed: ${e instanceof Error ? e.message : "Network error"}`);
    } finally {
      setIsScanning(false);
    }
  };

  const handleOpenFinder = async () => {
    try {
      const res = await openSkillsFolder("plugins");
      if (res.ok) {
        showNotice("Opened Finder at system plugins folder.");
      } else {
        showNotice("Failed to open Finder.");
      }
    } catch {
      showNotice("Could not reveal folder in Finder.");
    }
  };

  const handleToggle = async (s: SkillItem) => {
    try {
      const updated = await toggleSkill(s.name, !(s.enabled ?? true));
      setSkills((prev) =>
        prev.map((item) => (item.name === s.name ? { ...item, enabled: updated.skill.enabled } : item))
      );
    } catch (e: unknown) {
      showNotice(`Failed to toggle: ${e instanceof Error ? e.message : "Error"}`);
    }
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`Delete skill '${name}'?`)) return;
    try {
      await deleteCustomSkill(name);
      setSkills((prev) => prev.filter((s) => s.name !== name));
      showNotice(`Skill '${name}' deleted.`);
    } catch (e: unknown) {
      showNotice(`Delete failed: ${e instanceof Error ? e.message : "Error"}`);
    }
  };

  const handleTestRun = async (s: SkillItem) => {
    setIsExecuting(true);
    setTestExecutionResult(null);
    try {
      const res = await executeSkill(s.name);
      setTestExecutionResult({
        skillName: s.name,
        ok: res.ok,
        stdout: res.stdout,
        stderr: res.stderr,
        message: res.message,
        guidance_preview: res.guidance_preview,
      });
      // Increment use count locally
      setSkills((prev) =>
        prev.map((item) => (item.name === s.name ? { ...item, use_count: item.use_count + 1 } : item))
      );
    } catch (e: unknown) {
      setTestExecutionResult({
        skillName: s.name,
        ok: false,
        message: e instanceof Error ? e.message : "Execution failed",
      });
    } finally {
      setIsExecuting(false);
    }
  };

  const handleCreateSkill = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customName.trim()) return;
    setIsCreating(true);
    try {
      const triggersList = customTriggers
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      const res = await createCustomSkill({
        name: customName.trim(),
        title: customTitle.trim() || undefined,
        description: customDescription.trim(),
        category: customCategory,
        triggers: triggersList,
        execution_type: customExecType,
        command: customCommand.trim() || undefined,
        content: customContent.trim(),
      });

      if (res.ok) {
        showNotice(`Custom skill '${res.skill.name}' created successfully!`);
        setIsAddModalOpen(false);
        // Reset form
        setCustomName("");
        setCustomTitle("");
        setCustomDescription("");
        setCustomTriggers("");
        setCustomCommand("");
        setCustomContent("");
        await fetchSkills();
      }
    } catch (e: unknown) {
      alert(`Error creating skill: ${e instanceof Error ? e.message : "Failed"}`);
    } finally {
      setIsCreating(false);
    }
  };

  const filteredSkills = useMemo(() => {
    return skills.filter((s) => {
      // Category filter
      if (selectedCategory !== "all") {
        if (selectedCategory === "custom") {
          if (s.category !== "custom" || s.builtin) return false;
        } else if (s.category !== selectedCategory) {
          return false;
        }
      }

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesName = s.name.toLowerCase().includes(q);
        const matchesTitle = (s.title || "").toLowerCase().includes(q);
        const matchesDesc = (s.description || "").toLowerCase().includes(q);
        const matchesTriggers = (s.triggers || []).some((t) => t.toLowerCase().includes(q));
        return matchesName || matchesTitle || matchesDesc || matchesTriggers;
      }

      return true;
    });
  }, [skills, selectedCategory, searchQuery]);

  const getCategoryIcon = (category?: string) => {
    switch (category) {
      case "superpowers":
        return <FiShield className="text-amber-400" size={16} />;
      case "anthropic-agent":
        return <FiFileText className="text-blue-400" size={16} />;
      case "connect-apps":
        return <FiFolder className="text-emerald-400" size={16} />;
      case "linkedin":
        return <FiCode className="text-cyan-400" size={16} />;
      case "marketing":
        return <FiZap className="text-rose-400" size={16} />;
      case "reverse-engineering":
        return <FiTerminal className="text-orange-400" size={16} />;
      case "plugins":
        return <FiLayers className="text-indigo-400" size={16} />;
      case "custom":
        return <FiTerminal className="text-purple-400" size={16} />;
      default:
        return <FiZap className="text-ember" size={16} />;
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-5 pb-16">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <PageHeader
          title="Execution Skills Engine"
          mode="live"
          description="High-frequency action patterns and verified agent skills compiled into direct executables. Bypasses multi-step LLM loops for instant autonomous execution."
        />

        {/* Primary Action Buttons */}
        <div className="flex items-center gap-2 self-start sm:self-auto shrink-0">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void handleOpenFinder()}
            title="Reveal Plugins folder in macOS Finder"
            className="flex items-center gap-1.5"
          >
            <FiFolder size={14} />
            <span>Open in Finder</span>
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => void handleScanAndInstall()}
            loading={isScanning}
            title="Scan and compile Superpowers, Anthropic Agent skills & local plugins"
            className="flex items-center gap-1.5"
          >
            <FiRefreshCw size={14} className={isScanning ? "animate-spin" : ""} />
            <span>Scan & Install All</span>
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={() => setIsAddModalOpen(true)}
            className="flex items-center gap-1.5 shadow-sm"
          >
            <FiPlus size={14} />
            <span>Add Custom Skill</span>
          </Button>
        </div>
      </div>

      {/* Notice Banner */}
      {statusNotice && (
        <div className="rounded-lg border border-ember/30 bg-ember/10 p-3 text-xs font-medium text-ink flex items-center justify-between animate-fadeIn">
          <span>{statusNotice}</span>
          <button
            type="button"
            onClick={() => setStatusNotice(null)}
            className="text-mute hover:text-ink text-sm ml-2"
          >
            ✕
          </button>
        </div>
      )}

      {/* Search and Category Tabs */}
      <div className="space-y-3">
        <div className="relative">
          <FiSearch className="absolute left-3.5 top-1/2 -translate-y-1/2 text-mute" size={15} />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search execution skills by name, trigger keywords, or purpose..."
            className="w-full rounded-lg border border-line bg-surface py-2.5 pl-10 pr-4 text-xs text-ink placeholder:text-mute/60 focus:border-ember focus:outline-none shadow-sm transition-all"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-mute hover:text-ink text-xs"
            >
              ✕
            </button>
          )}
        </div>

        {/* Category Pills */}
        <div className="flex flex-wrap items-center gap-2">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              type="button"
              onClick={() => setSelectedCategory(cat.id)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition-all ${
                selectedCategory === cat.id
                  ? "bg-ember text-white shadow-sm"
                  : "bg-surface border border-line text-mute hover:text-ink hover:border-line-raised"
              }`}
            >
              {cat.label}
            </button>
          ))}
          <span className="ml-auto text-[11px] font-mono text-mute">
            Showing {filteredSkills.length} of {skills.length} skills
          </span>
        </div>
      </div>

      {/* Skills Grid / List */}
      {loading ? (
        <div className="p-12 text-center text-xs text-mute flex items-center justify-center gap-2">
          <FiRefreshCw className="animate-spin text-ember" size={16} />
          <span>Loading execution skills registry...</span>
        </div>
      ) : filteredSkills.length === 0 ? (
        <Card className="p-8 text-center space-y-3">
          <FiLayers className="mx-auto text-mute/50" size={32} />
          <p className="text-sm font-medium text-ink">No skills matched your search</p>
          <p className="text-xs text-mute max-w-sm mx-auto">
            Try adjusting your search query, or click &ldquo;Scan &amp; Install All&rdquo; to auto-discover
            Superpowers and Anthropic skills from your machine.
          </p>
          <Button variant="secondary" size="sm" onClick={() => void handleScanAndInstall()}>
            Scan &amp; Install System Skills
          </Button>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {filteredSkills.map((s) => {
            const isEnabled = s.enabled ?? true;
            return (
              <Card
                key={s.id || s.name}
                className={`flex flex-col justify-between p-4 transition-all hover:border-line-raised ${
                  !isEnabled ? "opacity-60 bg-surface/50" : ""
                }`}
              >
                <div className="space-y-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="p-2 rounded-lg bg-surface-raised border border-line shrink-0">
                        {getCategoryIcon(s.category)}
                      </div>
                      <div className="min-w-0">
                        <h3 className="font-semibold text-xs text-ink truncate">
                          {s.title || s.name}
                        </h3>
                        <p className="font-mono text-[10px] text-mute truncate">{s.name}</p>
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      <StatusPill
                        state={isEnabled ? "SUCCESS" : "UNAVAILABLE"}
                        label={isEnabled ? "Active" : "Disabled"}
                      />
                      <button
                        type="button"
                        onClick={() => void handleToggle(s)}
                        className="text-mute hover:text-ink transition-colors ml-1"
                        title={isEnabled ? "Disable skill" : "Enable skill"}
                      >
                        {isEnabled ? (
                          <FiToggleRight size={20} className="text-ember" />
                        ) : (
                          <FiToggleLeft size={20} className="text-mute" />
                        )}
                      </button>
                    </div>
                  </div>

                  <p className="text-xs text-mute leading-relaxed line-clamp-2">
                    {s.description}
                  </p>

                  {/* Triggers list */}
                  {s.triggers && s.triggers.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 pt-1">
                      <span className="text-[10px] uppercase font-bold text-mute/60 tracking-wider">
                        Triggers:
                      </span>
                      {s.triggers.slice(0, 3).map((tr) => (
                        <span
                          key={tr}
                          className="px-1.5 py-0.5 rounded bg-surface-raised border border-line text-[10px] font-mono text-ink/80"
                        >
                          {tr}
                        </span>
                      ))}
                      {s.triggers.length > 3 && (
                        <span className="text-[10px] text-mute font-mono">
                          +{s.triggers.length - 3} more
                        </span>
                      )}
                    </div>
                  )}

                  {/* Command preview */}
                  {s.command && (
                    <div className="rounded bg-surface-raised border border-line p-1.5 text-[10px] font-mono text-mute truncate">
                      $ {s.command}
                    </div>
                  )}
                </div>

                {/* Footer Controls & Stats */}
                <div className="mt-3.5 flex items-center justify-between border-t border-line/60 pt-2.5">
                  <div className="flex items-center gap-2 text-[10px] font-mono text-mute">
                    <span className="flex items-center gap-1">
                      <FiCheckCircle size={10} className="text-success" />
                      {s.use_count} runs
                    </span>
                    {s.builtin && (
                      <span className="inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded bg-emerald-500/10 border border-emerald-500/30 text-[9px] font-semibold text-emerald-400">
                        <FiCheckCircle size={9} /> Inbuilt
                      </span>
                    )}
                    {s.category && (
                      <span className="px-1.5 py-0.2 rounded bg-surface-raised border border-line text-[9px] uppercase font-bold text-mute">
                        {s.category}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setActiveDetailSkill(s)}
                      title="View full skill details and markdown instructions"
                      className="px-2 py-1 text-[11px]"
                    >
                      <FiCode size={11} className="mr-1" /> Details
                    </Button>

                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => void handleTestRun(s)}
                      disabled={!isEnabled || isExecuting}
                      title="Execute skill test run"
                      className="px-2 py-1 text-[11px]"
                    >
                      <FiPlay size={10} className="mr-1 text-ember" /> Test
                    </Button>

                    {s.category === "custom" && !s.builtin && (
                      <button
                        type="button"
                        onClick={() => void handleDelete(s.name)}
                        className="p-1 text-mute hover:text-danger transition-colors rounded"
                        title="Delete custom skill"
                      >
                        <FiTrash2 size={13} />
                      </button>
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Test Execution Output Modal */}
      {testExecutionResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-void/75 backdrop-blur-sm p-4 animate-fadeIn">
          <div className="w-full max-w-lg rounded-xl border border-line bg-surface p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div
                  className={`p-2 rounded-lg border ${
                    testExecutionResult.ok
                      ? "bg-success/10 border-success/30 text-success"
                      : "bg-danger/10 border-danger/30 text-danger"
                  }`}
                >
                  <FiTerminal size={16} />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-ink">
                    Test Execution: {testExecutionResult.skillName}
                  </h3>
                  <p className="text-[11px] text-mute">
                    Status: {testExecutionResult.ok ? "Success ✓" : "Failed ✕"}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setTestExecutionResult(null)}
                className="text-mute hover:text-ink text-sm p-1"
              >
                ✕
              </button>
            </div>

            {testExecutionResult.message && (
              <p className="text-xs text-ink/90 bg-surface-raised p-2.5 rounded border border-line">
                {testExecutionResult.message}
              </p>
            )}

            {testExecutionResult.stdout && (
              <div className="space-y-1">
                <span className="text-[10px] uppercase font-bold text-mute">STDOUT:</span>
                <pre className="p-3 rounded-lg bg-void/90 text-emerald-400 font-mono text-xs overflow-x-auto max-h-48 border border-line">
                  {testExecutionResult.stdout}
                </pre>
              </div>
            )}

            {testExecutionResult.stderr && (
              <div className="space-y-1">
                <span className="text-[10px] uppercase font-bold text-danger">STDERR:</span>
                <pre className="p-3 rounded-lg bg-void/90 text-danger font-mono text-xs overflow-x-auto max-h-36 border border-line">
                  {testExecutionResult.stderr}
                </pre>
              </div>
            )}

            {testExecutionResult.guidance_preview && (
              <div className="space-y-1">
                <span className="text-[10px] uppercase font-bold text-mute">Guidance Plan:</span>
                <div className="p-3 rounded-lg bg-surface-raised font-sans text-xs text-ink/80 border border-line">
                  {testExecutionResult.guidance_preview}
                </div>
              </div>
            )}

            <div className="flex justify-end pt-2">
              <Button
                variant="primary"
                size="sm"
                onClick={() => setTestExecutionResult(null)}
              >
                Close
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Skill Detail View Modal */}
      {activeDetailSkill && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-void/75 backdrop-blur-sm p-4 animate-fadeIn">
          <div className="w-full max-w-xl max-h-[85vh] flex flex-col rounded-xl border border-line bg-surface p-5 space-y-4 shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between border-b border-line pb-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-surface-raised border border-line">
                  {getCategoryIcon(activeDetailSkill.category)}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-ink">
                      {activeDetailSkill.title || activeDetailSkill.name}
                    </h3>
                    {activeDetailSkill.builtin && (
                      <span className="inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded bg-emerald-500/10 border border-emerald-500/30 text-[9px] font-semibold text-emerald-400">
                        <FiCheckCircle size={9} /> Inbuilt
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] font-mono text-mute">{activeDetailSkill.name}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setActiveDetailSkill(null)}
                className="text-mute hover:text-ink text-sm p-1"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-3.5 pr-1">
              <div>
                <span className="text-[10px] uppercase font-bold text-mute">Description:</span>
                <p className="text-xs text-ink mt-0.5 leading-relaxed">
                  {activeDetailSkill.description}
                </p>
              </div>

              {activeDetailSkill.triggers && activeDetailSkill.triggers.length > 0 && (
                <div>
                  <span className="text-[10px] uppercase font-bold text-mute">Triggers:</span>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {activeDetailSkill.triggers.map((t) => (
                      <span
                        key={t}
                        className="px-2 py-0.5 rounded bg-surface-raised border border-line text-xs font-mono text-ink"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {activeDetailSkill.source_path && (
                <div>
                  <span className="text-[10px] uppercase font-bold text-mute">Source Path:</span>
                  <p className="text-[11px] font-mono text-mute bg-surface-raised p-2 rounded border border-line truncate">
                    {activeDetailSkill.source_path}
                  </p>
                </div>
              )}

              {activeDetailSkill.content && (
                <div>
                  <span className="text-[10px] uppercase font-bold text-mute">Instructions &amp; Content:</span>
                  <pre className="p-3.5 rounded-lg bg-void/90 text-ink/90 font-mono text-xs overflow-x-auto max-h-64 border border-line whitespace-pre-wrap">
                    {activeDetailSkill.content}
                  </pre>
                </div>
              )}
            </div>

            <div className="flex items-center justify-between border-t border-line pt-3">
              <span className="text-[11px] font-mono text-mute">
                Total executions: {activeDetailSkill.use_count}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    const sk = activeDetailSkill;
                    setActiveDetailSkill(null);
                    void handleTestRun(sk);
                  }}
                >
                  <FiPlay size={11} className="mr-1 text-ember" /> Run Test
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setActiveDetailSkill(null)}
                >
                  Close
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add Custom Skill Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-void/75 backdrop-blur-sm p-4 animate-fadeIn">
          <div className="w-full max-w-lg rounded-xl border border-line bg-surface p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-line pb-3">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded bg-surface-raised border border-line text-ember">
                  <FiPlus size={16} />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-ink">Create Custom Execution Skill</h3>
                  <p className="text-xs text-mute">
                    Define a deterministic script, terminal command, or agent execution plan.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsAddModalOpen(false)}
                className="text-mute hover:text-ink text-sm p-1"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateSkill} className="space-y-3.5">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-ink">Skill Slug (ID) *</label>
                  <input
                    type="text"
                    value={customName}
                    onChange={(e) => setCustomName(e.target.value)}
                    placeholder="e.g. run-e2e-suite"
                    className="w-full rounded border border-line bg-surface-raised px-3 py-2 text-xs text-ink placeholder:text-mute/60 focus:border-ember focus:outline-none"
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-ink">Display Title</label>
                  <input
                    type="text"
                    value={customTitle}
                    onChange={(e) => setCustomTitle(e.target.value)}
                    placeholder="e.g. Run E2E Test Suite"
                    className="w-full rounded border border-line bg-surface-raised px-3 py-2 text-xs text-ink placeholder:text-mute/60 focus:border-ember focus:outline-none"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-ink">Description *</label>
                <textarea
                  value={customDescription}
                  onChange={(e) => setCustomDescription(e.target.value)}
                  placeholder="Explain when SAM should use this skill..."
                  rows={2}
                  className="w-full rounded border border-line bg-surface-raised px-3 py-2 text-xs text-ink placeholder:text-mute/60 focus:border-ember focus:outline-none"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-ink">Category</label>
                  <select
                    value={customCategory}
                    onChange={(e) => setCustomCategory(e.target.value)}
                    className="w-full rounded border border-line bg-surface-raised px-3 py-2 text-xs text-ink focus:border-ember focus:outline-none"
                  >
                    <option value="custom">Custom</option>
                    <option value="superpowers">Superpowers</option>
                    <option value="automation">Automation</option>
                    <option value="developer">Developer</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-ink">Execution Type</label>
                  <select
                    value={customExecType}
                    onChange={(e) => setCustomExecType(e.target.value)}
                    className="w-full rounded border border-line bg-surface-raised px-3 py-2 text-xs text-ink focus:border-ember focus:outline-none"
                  >
                    <option value="system_command">Terminal / Shell Command</option>
                    <option value="script">Script (Python / Node)</option>
                    <option value="prompt_template">Prompt Guide / Agent Workflow</option>
                  </select>
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-ink">Trigger Keywords</label>
                <input
                  type="text"
                  value={customTriggers}
                  onChange={(e) => setCustomTriggers(e.target.value)}
                  placeholder="Comma-separated (e.g. run tests, test suite, e2e)"
                  className="w-full rounded border border-line bg-surface-raised px-3 py-2 text-xs text-ink placeholder:text-mute/60 focus:border-ember focus:outline-none"
                />
              </div>

              {customExecType !== "prompt_template" && (
                <div className="space-y-1">
                  <label className="text-xs font-medium text-ink">Command to Execute</label>
                  <input
                    type="text"
                    value={customCommand}
                    onChange={(e) => setCustomCommand(e.target.value)}
                    placeholder="e.g. npm test -- --run"
                    className="w-full rounded border border-line bg-surface-raised px-3 py-2 text-xs font-mono text-ink placeholder:text-mute/60 focus:border-ember focus:outline-none"
                  />
                </div>
              )}

              <div className="space-y-1">
                <label className="text-xs font-medium text-ink">Instructions / Guidance (Markdown)</label>
                <textarea
                  value={customContent}
                  onChange={(e) => setCustomContent(e.target.value)}
                  placeholder="Provide step-by-step instructions or rules for SAM..."
                  rows={3}
                  className="w-full rounded border border-line bg-surface-raised px-3 py-2 text-xs font-mono text-ink placeholder:text-mute/60 focus:border-ember focus:outline-none"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-line">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsAddModalOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  loading={isCreating}
                >
                  Save &amp; Compile Skill
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
