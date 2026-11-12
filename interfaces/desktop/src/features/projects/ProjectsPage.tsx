import { useEffect, useState, useCallback } from "react";
import { FiFolder, FiPlus, FiTrash2, FiMessageSquare } from "react-icons/fi";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { listProjects, saveProject, deleteProject, type ProjectItem } from "@/api/client";

export function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [folderPath, setFolderPath] = useState("");
  const [context, setContext] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const navigate = useNavigate();

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listProjects();
      setProjects(res.projects || []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !folderPath.trim()) return;
    setSaving(true);
    try {
      await saveProject({
        name: name.trim(),
        folder_path: folderPath.trim(),
        context: context.trim(),
      });
      setName("");
      setFolderPath("");
      setContext("");
      setShowCreate(false);
      await refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save project");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteProject(id);
      await refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to delete project");
    }
  };

  const handleOpenInChat = (project: ProjectItem) => {
    localStorage.setItem("sam.desktop.active_project", JSON.stringify(project));
    navigate("/chat");
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6 pb-12">
      <div className="flex items-center justify-between">
        <PageHeader
          title="Projects & Folders"
          mode="live"
          description="Group tasks and conversations with folder paths and custom system instructions. SAM automatically aligns its context to your project."
        />
        <Button variant="primary" size="sm" onClick={() => setShowCreate(!showCreate)}>
          <FiPlus size={14} /> New Project
        </Button>
      </div>

      {error && (
        <div className="rounded border border-danger/30 bg-danger/10 p-3 text-xs text-danger">
          {error}
        </div>
      )}

      {/* Project Creator Drawer */}
      {showCreate && (
        <Card className="space-y-4 border-ember/40 bg-surface">
          <div className="flex items-center justify-between border-b border-line pb-2.5">
            <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
              <FiFolder className="text-ember" /> Create Workspace Project
            </h3>
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              className="text-xs text-mute hover:text-ink"
            >
              Cancel
            </button>
          </div>

          <form onSubmit={handleSave} className="space-y-3.5">
            <div>
              <label className="block text-xs font-medium text-ink mb-1">Project Name</label>
              <input
                type="text"
                placeholder="e.g. SAM Core Engine or Thesis Research"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded border border-line bg-surface-raised px-3 py-1.5 text-xs text-ink focus:border-ember focus:outline-none"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-ink mb-1">Working Directory / Folder Path</label>
              <input
                type="text"
                placeholder="e.g. /Users/dhanushsurada/Projects/SAM or ~/Desktop/ClientSite"
                value={folderPath}
                onChange={(e) => setFolderPath(e.target.value)}
                className="w-full rounded border border-line bg-surface-raised px-3 py-1.5 text-xs font-mono-data text-ink focus:border-ember focus:outline-none"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-ink mb-1">
                Custom Context & Instructions <span className="text-mute font-normal">(Optional)</span>
              </label>
              <textarea
                placeholder="Specific rules, preferred tech stack, code formatting style, or personal constraints..."
                value={context}
                onChange={(e) => setContext(e.target.value)}
                rows={3}
                className="w-full rounded border border-line bg-surface-raised px-3 py-2 text-xs text-ink focus:border-ember focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-1">
              <Button type="button" variant="ghost" size="sm" onClick={() => setShowCreate(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" size="sm" loading={saving}>
                Save Project
              </Button>
            </div>
          </form>
        </Card>
      )}

      {/* Projects List */}
      {loading ? (
        <div className="py-12 text-center text-xs text-mute">Loading projects...</div>
      ) : projects.length === 0 ? (
        <div className="rounded-lg border border-dashed border-line p-8 text-center space-y-3">
          <FiFolder size={32} className="mx-auto text-mute/50" />
          <div>
            <p className="text-sm font-medium text-ink">No projects defined yet</p>
            <p className="text-xs text-mute mt-1">
              Create a project to bind SAM to a specific codebase, documents folder, or research directory.
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => setShowCreate(true)}>
            <FiPlus size={14} /> Add your first project
          </Button>
        </div>
      ) : (
        <div className="grid gap-3.5">
          {projects.map((proj) => (
            <div
              key={proj.id}
              className="rounded-lg border border-line bg-surface p-4 transition-colors hover:border-line-active space-y-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <FiFolder className="text-amber-400" size={16} />
                    <h3 className="text-sm font-semibold text-ink">{proj.name}</h3>
                  </div>
                  <p className="font-mono-data text-[11px] text-mute flex items-center gap-1">
                    <span>Path:</span>
                    <span className="text-ink/80">{proj.folder_path}</span>
                  </p>
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleOpenInChat(proj)}
                    title="Open dedicated chat with this project's context"
                  >
                    <FiMessageSquare size={13} /> Chat
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(proj.id)}
                    className="text-mute hover:text-danger"
                    title="Delete Project"
                  >
                    <FiTrash2 size={13} />
                  </Button>
                </div>
              </div>

              {proj.context && (
                <div className="rounded bg-surface-raised/70 border border-line p-2 text-xs text-mute font-mono-data">
                  <span className="text-ink font-sans font-medium text-[11px] block mb-0.5">Context:</span>
                  <p className="text-xs line-clamp-2">{proj.context}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
