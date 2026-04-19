"use client";

import { Fragment, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  Database,
  FileAudio,
  Loader2,
  Mic2,
  Pencil,
  RefreshCcw,
  Trash2,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

const ADMIN_REFRESH_INTERVAL_MS = 5000;

type Speaker = {
  id: number;
  name: string;
  embedding_count: number;
  embedded_audio_count: number;
  raw_audio_count: number;
  pending_audio_count: number;
  running_audio_count: number;
  failed_audio_count: number;
  no_speech_audio_count: number;
  succeeded_audio_count: number;
  created_at: string;
};

type SpeakerAudioAsset = {
  id: number;
  speaker_id: number;
  original_filename: string;
  storage_key: string;
  processing_status: "pending" | "running" | "failed" | "no_speech" | "succeeded" | string;
  processing_error: string | null;
  processing_started_at: string | null;
  processing_finished_at: string | null;
  has_speech: boolean;
  created_at: string;
  embedding_count: number;
};

type DeletePreview = {
  audio_asset_count: number;
  embedding_count: number;
  minio_object_count: number;
  speaker_name?: string;
  original_filename?: string;
};

export default function AdminPage() {
  const t = useTranslations("admin");
  const tCommon = useTranslations("common");

  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<Record<number, string>>({});
  const [renameSaving, setRenameSaving] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [deletingAssetId, setDeletingAssetId] = useState<number | null>(null);
  const [housekeeping, setHousekeeping] = useState(false);
  const [expandedSpeakerIds, setExpandedSpeakerIds] = useState<Record<number, boolean>>({});
  const [speakerAssets, setSpeakerAssets] = useState<Record<number, SpeakerAudioAsset[]>>({});
  const [loadingAssets, setLoadingAssets] = useState<Record<number, boolean>>({});
  const [statusMsg, setStatusMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  // New states for custom dialogs
  const [deleteSpeakerConfirm, setDeleteSpeakerConfirm] = useState<{
    speaker: Speaker;
    preview: DeletePreview;
  } | null>(null);
  const [deleteAssetConfirm, setDeleteAssetConfirm] = useState<{
    speakerId: number;
    assetId: number;
    filename: string;
    preview: DeletePreview;
  } | null>(null);

  function toast(type: "ok" | "err", text: string) {
    setStatusMsg({ type, text });
    setTimeout(() => setStatusMsg(null), 3500);
  }

  function renderStatusBadges(speaker: Speaker) {
    if (speaker.raw_audio_count === 0) {
      return <Badge variant="outline">{t("status_empty")}</Badge>;
    }

    const badges: Array<{
      key: string;
      text: string;
      variant: "secondary" | "default" | "destructive" | "outline" | "success";
    }> = [];

    if (speaker.pending_audio_count > 0) {
      badges.push({
        key: "pending",
        text: t("status_pending_n", { count: speaker.pending_audio_count }),
        variant: "secondary",
      });
    }
    if (speaker.running_audio_count > 0) {
      badges.push({
        key: "running",
        text: t("status_running_n", { count: speaker.running_audio_count }),
        variant: "default",
      });
    }
    if (speaker.failed_audio_count > 0) {
      badges.push({
        key: "failed",
        text: t("status_failed_n", { count: speaker.failed_audio_count }),
        variant: "destructive",
      });
    }
    if (speaker.no_speech_audio_count > 0) {
      badges.push({
        key: "no-speech",
        text: t("status_no_speech_n", { count: speaker.no_speech_audio_count }),
        variant: "outline",
      });
    }
    if (badges.length === 0) {
      badges.push({
        key: "done",
        text: t("status_done_n", { count: speaker.succeeded_audio_count || speaker.embedded_audio_count }),
        variant: "success",
      });
    }

    return (
      <div className="flex flex-wrap gap-1.5">
        {badges.map((badge) => (
          <Badge key={badge.key} variant={badge.variant}>
            {badge.text}
          </Badge>
        ))}
      </div>
    );
  }

  function renderAssetStatusBadge(asset: SpeakerAudioAsset) {
    switch (asset.processing_status) {
      case "pending":
        return <Badge variant="secondary">{t("asset_status_pending")}</Badge>;
      case "running":
        return <Badge variant="default">{t("asset_status_running")}</Badge>;
      case "failed":
        return <Badge variant="destructive">{t("asset_status_failed")}</Badge>;
      case "no_speech":
        return <Badge variant="outline">{t("asset_status_no_speech")}</Badge>;
      case "succeeded":
        return <Badge variant="success">{t("asset_status_succeeded")}</Badge>;
      default:
        return <Badge variant="outline">{asset.processing_status}</Badge>;
    }
  }

  async function fetchSpeakers(showLoading = true) {
    if (showLoading) {
      setLoading(true);
    }

    try {
      const res = await fetch("/api/speakers");
      const data = await res.json().catch(() => ({ detail: tCommon("unknown_error") }));
      if (!res.ok) {
        throw new Error(data.detail ?? tCommon("unknown_error"));
      }

      const next = Array.isArray(data.speakers) ? [...data.speakers] : [];
      next.sort((left, right) => right.id - left.id);
      setSpeakers(next);
      setError(null);
    } catch (fetchError: unknown) {
      setError(fetchError instanceof Error ? fetchError.message : tCommon("unknown_error"));
    } finally {
      if (showLoading) {
        setLoading(false);
      }
    }
  }

  async function fetchSpeakerAssets(speakerId: number) {
    setLoadingAssets((prev) => ({ ...prev, [speakerId]: true }));

    try {
      const res = await fetch(`/api/speakers/${speakerId}/audio-assets`);
      const data = await res.json().catch(() => ({ detail: tCommon("unknown_error") }));
      if (!res.ok) {
        throw new Error(data.detail ?? tCommon("unknown_error"));
      }

      setSpeakerAssets((prev) => ({
        ...prev,
        [speakerId]: Array.isArray(data.audio_assets) ? data.audio_assets : [],
      }));
    } catch (fetchError: unknown) {
      toast("err", fetchError instanceof Error ? fetchError.message : tCommon("unknown_error"));
    } finally {
      setLoadingAssets((prev) => ({ ...prev, [speakerId]: false }));
    }
  }

  useEffect(() => {
    void fetchSpeakers();
    const timer = window.setInterval(() => {
      void fetchSpeakers(false);
      Object.entries(expandedSpeakerIds)
        .filter(([, expanded]) => expanded)
        .forEach(([speakerId]) => {
          void fetchSpeakerAssets(Number(speakerId));
        });
    }, ADMIN_REFRESH_INTERVAL_MS);

    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expandedSpeakerIds]);

  function startRename(speaker: Speaker) {
    setRenaming((prev) => ({ ...prev, [speaker.id]: speaker.name }));
  }

  function cancelRename(id: number) {
    setRenaming((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }

  async function toggleSpeakerAssets(speakerId: number) {
    const nextExpanded = !expandedSpeakerIds[speakerId];
    setExpandedSpeakerIds((prev) => ({ ...prev, [speakerId]: nextExpanded }));
    if (nextExpanded && !speakerAssets[speakerId]) {
      await fetchSpeakerAssets(speakerId);
    }
  }

  async function saveRename(id: number) {
    const newName = (renaming[id] ?? "").trim();
    if (!newName) {
      return;
    }

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

      setSpeakers((prev) => prev.map((speaker) => (speaker.id === id ? { ...speaker, name: newName } : speaker)));
      cancelRename(id);
      toast("ok", t("renamed_success"));
    } catch (saveError: unknown) {
      toast("err", saveError instanceof Error ? saveError.message : tCommon("unknown_error"));
    } finally {
      setRenameSaving(null);
    }
  }

  function buildDeleteMessage(title: string, preview: DeletePreview) {
    return [
      title,
      t("confirm_delete_audio_count", { count: preview.audio_asset_count }),
      t("confirm_delete_object_count", { count: preview.minio_object_count }),
      t("confirm_delete_vector_count", { count: preview.embedding_count }),
      t("confirm_delete_continue"),
    ].join("\n");
  }

  async function fetchSpeakerDeletePreview(speakerId: number): Promise<DeletePreview> {
    const res = await fetch(`/api/speakers/${speakerId}/delete-preview`);
    const data = await res.json().catch(() => ({ detail: tCommon("unknown_error") }));
    if (!res.ok) {
      throw new Error(data.detail ?? tCommon("unknown_error"));
    }
    return data as DeletePreview;
  }

  async function fetchAssetDeletePreview(speakerId: number, assetId: number): Promise<DeletePreview> {
    const res = await fetch(`/api/speakers/${speakerId}/audio-assets/${assetId}/delete-preview`);
    const data = await res.json().catch(() => ({ detail: tCommon("unknown_error") }));
    if (!res.ok) {
      throw new Error(data.detail ?? tCommon("unknown_error"));
    }
    return data as DeletePreview;
  }

  async function deleteSpeaker(speaker: Speaker) {
    try {
      const preview = await fetchSpeakerDeletePreview(speaker.id);
      setDeleteSpeakerConfirm({ speaker, preview });
    } catch (deleteError: unknown) {
      toast("err", deleteError instanceof Error ? deleteError.message : tCommon("unknown_error"));
    }
  }

  async function confirmDeleteSpeaker() {
    if (!deleteSpeakerConfirm) return;
    const { speaker } = deleteSpeakerConfirm;

    setDeleting(speaker.id);
    setDeleteSpeakerConfirm(null);
    try {
      const res = await fetch(`/api/speakers/${speaker.id}`, { method: "DELETE" });
      if (res.status !== 204 && !res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? "Delete failed");
      }

      setSpeakers((prev) => prev.filter((item) => item.id !== speaker.id));
      setExpandedSpeakerIds((prev) => {
        const next = { ...prev };
        delete next[speaker.id];
        return next;
      });
      setSpeakerAssets((prev) => {
        const next = { ...prev };
        delete next[speaker.id];
        return next;
      });
      toast("ok", t("deleted_success"));
    } catch (deleteError: unknown) {
      toast("err", deleteError instanceof Error ? deleteError.message : tCommon("unknown_error"));
    } finally {
      setDeleting(null);
    }
  }

  async function runHousekeep() {
    setHousekeeping(true);
    try {
      const res = await fetch("/api/speakers/housekeep", { method: "POST" });
      const data = await res.json().catch(() => ({ detail: res.statusText }));
      if (!res.ok) {
        throw new Error(data.detail ?? tCommon("unknown_error"));
      }

      await fetchSpeakers(false);
      await Promise.all(
        Object.entries(expandedSpeakerIds)
          .filter(([, expanded]) => expanded)
          .map(([speakerId]) => fetchSpeakerAssets(Number(speakerId))),
      );

      toast(
        "ok",
        t("housekeep_success", {
          assets: data.deleted_db_assets ?? 0,
          objects: data.deleted_minio_objects ?? 0,
          embeddings: data.deleted_embeddings ?? 0,
        }),
      );
    } catch (housekeepError: unknown) {
      toast("err", housekeepError instanceof Error ? housekeepError.message : tCommon("unknown_error"));
    } finally {
      setHousekeeping(false);
    }
  }

  async function deleteAsset(speakerId: number, assetId: number, originalFilename: string) {
    try {
      const preview = await fetchAssetDeletePreview(speakerId, assetId);
      setDeleteAssetConfirm({
        speakerId,
        assetId,
        filename: originalFilename,
        preview,
      });
    } catch (deleteError: unknown) {
      toast("err", deleteError instanceof Error ? deleteError.message : tCommon("unknown_error"));
    }
  }

  async function confirmDeleteAsset() {
    if (!deleteAssetConfirm) return;
    const { speakerId, assetId } = deleteAssetConfirm;

    setDeletingAssetId(assetId);
    setDeleteAssetConfirm(null);
    try {
      const res = await fetch(`/api/speakers/${speakerId}/audio-assets/${assetId}`, {
        method: "DELETE",
      });
      const data = await res.json().catch(() => ({ detail: res.statusText }));
      if (!res.ok) {
        throw new Error(data.detail ?? tCommon("unknown_error"));
      }

      await fetchSpeakers(false);
      await fetchSpeakerAssets(speakerId);
      toast("ok", t("asset_deleted_success"));
    } catch (deleteError: unknown) {
      toast("err", deleteError instanceof Error ? deleteError.message : tCommon("unknown_error"));
    } finally {
      setDeletingAssetId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t("title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={() => void runHousekeep()}
          disabled={housekeeping}
          className="self-start"
        >
          {housekeeping ? (
            <Loader2 className="mr-2 size-3.5 animate-spin" />
          ) : (
            <RefreshCcw className="mr-2 size-3.5" />
          )}
          {housekeeping ? t("housekeep_running") : t("housekeep")}
        </Button>
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
        <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="w-16 px-4 py-2 text-left font-medium text-muted-foreground">{t("id")}</th>
                <th className="px-4 py-2 text-left font-medium text-muted-foreground">{t("name_col")}</th>
                <th className="w-28 px-4 py-2 text-left font-medium text-muted-foreground">{t("raw_audio")}</th>
                <th className="w-32 px-4 py-2 text-left font-medium text-muted-foreground">
                  {t("completed_embeddings")}
                </th>
                <th className="min-w-52 px-4 py-2 text-left font-medium text-muted-foreground">
                  {t("background_processing")}
                </th>
                <th className="w-40 px-4 py-2 text-left font-medium text-muted-foreground">{t("created_at")}</th>
                <th className="w-40 px-4 py-2 text-right font-medium text-muted-foreground">{t("actions")}</th>
              </tr>
            </thead>
            <tbody>
              {speakers.map((speaker) => {
                const isRenaming = speaker.id in renaming;
                const isExpanded = !!expandedSpeakerIds[speaker.id];
                const assets = speakerAssets[speaker.id] ?? [];
                const isLoadingAssets = !!loadingAssets[speaker.id];

                return (
                  <Fragment key={speaker.id}>
                    <tr
                      className="border-b border-border last:border-0 hover:bg-muted/20 transition-colors cursor-pointer"
                      onClick={() => void toggleSpeakerAssets(speaker.id)}
                    >
                      <td className="px-4 py-3 text-muted-foreground">{speaker.id}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-start gap-2">
                          <div className="min-w-0 flex-1">
                            {isRenaming ? (
                              <Input
                                value={renaming[speaker.id]}
                                onClick={(e) => e.stopPropagation()}
                                onChange={(event) =>
                                  setRenaming((prev) => ({ ...prev, [speaker.id]: event.target.value }))
                                }
                                onKeyDown={(event) => {
                                  if (event.key === "Enter") {
                                    void saveRename(speaker.id);
                                  }
                                  if (event.key === "Escape") {
                                    cancelRename(speaker.id);
                                  }
                                }}
                                className="h-7 max-w-xs text-sm"
                                autoFocus
                              />
                            ) : (
                              <span className="font-medium">{speaker.name}</span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant="secondary">{speaker.raw_audio_count}</Badge>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={speaker.embedded_audio_count > 0 ? "success" : "outline"}>
                          {speaker.embedded_audio_count}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <div className="space-y-1.5">
                          {renderStatusBadges(speaker)}
                          <p className="text-xs text-muted-foreground">
                            {t("vector_count", { count: speaker.embedding_count })}
                          </p>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {new Date(speaker.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-3">
                        {isRenaming ? (
                          <div
                            className="flex items-center justify-end gap-1"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => void saveRename(speaker.id)}
                              disabled={renameSaving === speaker.id || !renaming[speaker.id]?.trim()}
                              className="h-7 px-2"
                            >
                              <Check className="size-3" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => cancelRename(speaker.id)}
                              className="h-7 px-2"
                            >
                              <X className="size-3" />
                            </Button>
                          </div>
                        ) : (
                          <div
                            className="flex items-center justify-end gap-1"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => startRename(speaker)}
                              className="h-7 px-2 text-muted-foreground hover:text-foreground"
                              title={t("rename")}
                            >
                              <Pencil className="size-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => void deleteSpeaker(speaker)}
                              disabled={deleting === speaker.id}
                              className="h-7 px-2 text-muted-foreground hover:text-destructive"
                              title={t("delete")}
                            >
                              <Trash2 className="size-3.5" />
                            </Button>
                          </div>
                        )}
                      </td>
                    </tr>

                    {isExpanded && (
                      <tr className="border-b border-border bg-muted/10 last:border-0">
                        <td colSpan={7} className="px-4 py-4">
                          <div className="space-y-3">
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-sm font-medium">{t("audio_files")}</p>
                              {isLoadingAssets && (
                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                  <Loader2 className="size-3.5 animate-spin" />
                                  {t("audio_loading")}
                                </div>
                              )}
                            </div>

                            {!isLoadingAssets && assets.length === 0 && (
                              <p className="text-sm text-muted-foreground">{t("no_audio_files")}</p>
                            )}

                            <div className="space-y-3">
                              {assets.map((asset) => (
                                <div
                                  key={asset.id}
                                  className="grid gap-3 rounded-lg border border-border bg-background/80 p-3 md:grid-cols-[minmax(0,1fr)_minmax(260px,320px)_auto]"
                                >
                                  <div className="min-w-0 space-y-1.5">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <p className="break-all font-medium">{asset.original_filename}</p>
                                      {renderAssetStatusBadge(asset)}
                                    </div>
                                    <p className="text-xs text-muted-foreground">
                                      ID {asset.id} · {new Date(asset.created_at).toLocaleString()} · {t("asset_vector_count", { count: asset.embedding_count })}
                                    </p>
                                    {asset.processing_error && (
                                      <p className="break-all text-xs text-destructive">{asset.processing_error}</p>
                                    )}
                                  </div>

                                  <div className="min-w-0" onClick={(e) => e.stopPropagation()}>
                                    <p className="mb-1 text-xs font-medium text-muted-foreground">
                                      {t("audio_preview")}
                                    </p>
                                    <audio
                                      controls
                                      preload="none"
                                      className="h-9 w-full rounded-md bg-muted/20"
                                      src={`/api/speakers/${speaker.id}/audio-assets/${asset.id}/audio`}
                                    />
                                  </div>

                                  <div className="flex items-start justify-end" onClick={(e) => e.stopPropagation()}>
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => void deleteAsset(speaker.id, asset.id, asset.original_filename)}
                                      disabled={deletingAssetId === asset.id}
                                      className="h-8 px-2 text-muted-foreground hover:text-destructive"
                                      title={t("delete_asset")}
                                    >
                                      {deletingAssetId === asset.id ? (
                                        <Loader2 className="size-3.5 animate-spin" />
                                      ) : (
                                        <Trash2 className="size-3.5" />
                                      )}
                                    </Button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Delete Speaker Confirmation Dialog */}
      <Dialog
        open={!!deleteSpeakerConfirm}
        onClose={() => setDeleteSpeakerConfirm(null)}
        title={t("confirm_delete_short")}
        className="sm:max-w-[440px]"
      >
        {deleteSpeakerConfirm && (
          <div className="space-y-6">
            <div className="flex gap-4">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                <AlertTriangle className="size-5" />
              </div>
              <div className="space-y-1">
                <p className="font-semibold leading-none">
                  {t("confirm_delete_speaker_title", {
                    name: deleteSpeakerConfirm.preview.speaker_name ?? deleteSpeakerConfirm.speaker.name,
                  })}
                </p>
                <p className="text-sm text-muted-foreground">
                  {t("confirm_delete_continue")}
                </p>
              </div>
            </div>

            <div className="rounded-xl border border-border bg-muted/30 p-4">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                影響資源預覽
              </p>
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <FileAudio className="size-3.5" />
                    <span className="text-xs">{t("raw_audio")}</span>
                  </div>
                  <p className="text-lg font-bold tabular-nums">
                    {deleteSpeakerConfirm.preview.audio_asset_count}
                  </p>
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <Mic2 className="size-3.5" />
                    <span className="text-xs">Vectors</span>
                  </div>
                  <p className="text-lg font-bold tabular-nums">
                    {deleteSpeakerConfirm.preview.embedding_count}
                  </p>
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <Database className="size-3.5" />
                    <span className="text-xs">Storage</span>
                  </div>
                  <p className="text-lg font-bold tabular-nums">
                    {deleteSpeakerConfirm.preview.minio_object_count}
                  </p>
                </div>
              </div>
            </div>

            <div className="flex gap-3">
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => setDeleteSpeakerConfirm(null)}
              >
                {t("cancel")}
              </Button>
              <Button
                variant="destructive"
                className="flex-1"
                onClick={() => void confirmDeleteSpeaker()}
              >
                {t("delete")}
              </Button>
            </div>
          </div>
        )}
      </Dialog>

      {/* Delete Asset Confirmation Dialog */}
      <Dialog
        open={!!deleteAssetConfirm}
        onClose={() => setDeleteAssetConfirm(null)}
        title={t("confirm_delete_short")}
        className="sm:max-w-[440px]"
      >
        {deleteAssetConfirm && (
          <div className="space-y-6">
            <div className="flex gap-4">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                <AlertTriangle className="size-5" />
              </div>
              <div className="space-y-1">
                <p className="font-semibold leading-none">
                  {t("confirm_delete_asset_title", {
                    name: deleteAssetConfirm.preview.original_filename ?? deleteAssetConfirm.filename,
                  })}
                </p>
                <p className="text-sm text-muted-foreground">
                  {t("confirm_delete_asset")}
                </p>
              </div>
            </div>

            <div className="rounded-xl border border-border bg-muted/30 p-4">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                影響資源預覽
              </p>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <Mic2 className="size-3.5" />
                    <span className="text-xs">Vectors</span>
                  </div>
                  <p className="text-lg font-bold tabular-nums">
                    {deleteAssetConfirm.preview.embedding_count}
                  </p>
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <Database className="size-3.5" />
                    <span className="text-xs">Storage</span>
                  </div>
                  <p className="text-lg font-bold tabular-nums">
                    {deleteAssetConfirm.preview.minio_object_count}
                  </p>
                </div>
              </div>
            </div>

            <div className="flex gap-3">
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => setDeleteAssetConfirm(null)}
              >
                {t("cancel")}
              </Button>
              <Button
                variant="destructive"
                className="flex-1"
                onClick={() => void confirmDeleteAsset()}
              >
                {t("delete")}
              </Button>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
}
