"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Pencil, Trash2, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

type Speaker = {
  id: number;
  name: string;
  embedding_count: number;
  created_at: string;
};

export default function AdminPage() {
  const t = useTranslations("admin");
  const tCommon = useTranslations("common");

  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Rename state: maps speaker id → draft name
  const [renaming, setRenaming] = useState<Record<number, string>>({});
  const [renameSaving, setRenameSaving] = useState<number | null>(null);

  // Delete state
  const [deleting, setDeleting] = useState<number | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  // Status messages
  const [statusMsg, setStatusMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  function toast(type: "ok" | "err", text: string) {
    setStatusMsg({ type, text });
    setTimeout(() => setStatusMsg(null), 3500);
  }

  async function fetchSpeakers() {
    setLoading(true);
    try {
      const res = await fetch("/api/speakers");
      const data = await res.json();
      setSpeakers(data.speakers ?? []);
    } catch {
      setError(tCommon("unknown_error"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchSpeakers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startRename(s: Speaker) {
    setRenaming((prev) => ({ ...prev, [s.id]: s.name }));
  }

  function cancelRename(id: number) {
    setRenaming((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }

  async function saveRename(id: number) {
    const newName = (renaming[id] ?? "").trim();
    if (!newName) return;
    setRenameSaving(id);
    try {
      const res = await fetch(`/api/speakers/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? "Rename failed");
      }
      setSpeakers((prev) => prev.map((s) => (s.id === id ? { ...s, name: newName } : s)));
      cancelRename(id);
      toast("ok", t("renamed_success"));
    } catch (e: unknown) {
      toast("err", e instanceof Error ? e.message : tCommon("unknown_error"));
    } finally {
      setRenameSaving(null);
    }
  }

  async function confirmDelete(id: number) {
    setDeleting(id);
    try {
      const res = await fetch(`/api/speakers/${id}`, { method: "DELETE" });
      if (res.status !== 204 && !res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? "Delete failed");
      }
      setSpeakers((prev) => prev.filter((s) => s.id !== id));
      setConfirmDeleteId(null);
      toast("ok", t("deleted_success"));
    } catch (e: unknown) {
      toast("err", e instanceof Error ? e.message : tCommon("unknown_error"));
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t("title")}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t("subtitle")}</p>
      </div>

      {statusMsg && (
        <div
          className={`rounded-lg border px-4 py-2 text-sm ${
            statusMsg.type === "ok"
              ? "border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-400"
              : "border-destructive/40 bg-destructive/10 text-destructive"
          }`}
        >
          {statusMsg.text}
        </div>
      )}

      {loading && <p className="text-sm text-muted-foreground">{t("loading")}</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}

      {!loading && speakers.length === 0 && (
        <p className="text-sm text-muted-foreground">{t("no_speakers")}</p>
      )}

      {!loading && speakers.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="px-4 py-2 text-left font-medium text-muted-foreground w-16">
                  {t("id")}
                </th>
                <th className="px-4 py-2 text-left font-medium text-muted-foreground">
                  {t("name_col")}
                </th>
                <th className="px-4 py-2 text-left font-medium text-muted-foreground w-28">
                  {t("embeddings")}
                </th>
                <th className="px-4 py-2 text-left font-medium text-muted-foreground w-40">
                  {t("created_at")}
                </th>
                <th className="px-4 py-2 text-right font-medium text-muted-foreground w-40">
                  {t("actions")}
                </th>
              </tr>
            </thead>
            <tbody>
              {speakers.map((s) => {
                const isRenaming = s.id in renaming;
                const isConfirmingDelete = confirmDeleteId === s.id;

                return (
                  <tr
                    key={s.id}
                    className="border-b border-border last:border-0 hover:bg-muted/20 transition-colors"
                  >
                    <td className="px-4 py-3 text-muted-foreground">{s.id}</td>

                    {/* Name cell */}
                    <td className="px-4 py-3">
                      {isRenaming ? (
                        <Input
                          value={renaming[s.id]}
                          onChange={(e) =>
                            setRenaming((prev) => ({ ...prev, [s.id]: e.target.value }))
                          }
                          onKeyDown={(e) => {
                            if (e.key === "Enter") saveRename(s.id);
                            if (e.key === "Escape") cancelRename(s.id);
                          }}
                          className="h-7 max-w-xs text-sm"
                          autoFocus
                        />
                      ) : (
                        <span className="font-medium">{s.name}</span>
                      )}
                    </td>

                    {/* Embeddings */}
                    <td className="px-4 py-3">
                      <Badge variant="secondary">{s.embedding_count}</Badge>
                    </td>

                    {/* Created at */}
                    <td className="px-4 py-3 text-muted-foreground">
                      {new Date(s.created_at).toLocaleDateString()}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3">
                      {isConfirmingDelete ? (
                        <div className="flex items-center justify-end gap-1">
                          <span className="text-xs text-destructive mr-1">{t("confirm_delete_short")}</span>
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => confirmDelete(s.id)}
                            disabled={deleting === s.id}
                            className="h-7 px-2 text-xs"
                          >
                            <Check className="size-3" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setConfirmDeleteId(null)}
                            className="h-7 px-2"
                          >
                            <X className="size-3" />
                          </Button>
                        </div>
                      ) : isRenaming ? (
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => saveRename(s.id)}
                            disabled={renameSaving === s.id || !renaming[s.id]?.trim()}
                            className="h-7 px-2"
                          >
                            <Check className="size-3" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => cancelRename(s.id)}
                            className="h-7 px-2"
                          >
                            <X className="size-3" />
                          </Button>
                        </div>
                      ) : (
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => startRename(s)}
                            className="h-7 px-2 text-muted-foreground hover:text-foreground"
                            title={t("rename")}
                          >
                            <Pencil className="size-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setConfirmDeleteId(s.id)}
                            className="h-7 px-2 text-muted-foreground hover:text-destructive"
                            title={t("delete")}
                          >
                            <Trash2 className="size-3.5" />
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
