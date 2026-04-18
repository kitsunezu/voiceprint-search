"use client";

import { useState, useEffect, useRef } from "react";
import { useTranslations } from "next-intl";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  X,
  ChevronDown,
  UserPlus,
  Users,
  Search as SearchIcon,
} from "lucide-react";
import { AudioUploader } from "@/components/AudioUploader";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

type Speaker = { id: number; name: string; embedding_count: number; created_at: string };
type FileStatus = "pending" | "uploading" | "done" | "error";
type QueuedFile = { key: string; file: File; status: FileStatus; message?: string };

export default function EnrollPage() {
  const t = useTranslations("enroll");
  const tCommon = useTranslations("common");

  const [name, setName] = useState("");
  const [queue, setQueue] = useState<QueuedFile[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [selectedSpeakerId, setSelectedSpeakerId] = useState<number | null>(null);
  const [dupDialogSpeaker, setDupDialogSpeaker] = useState<Speaker | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const comboRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("/api/speakers")
      .then((r) => r.json())
      .then((d) => setSpeakers(d.speakers ?? []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (comboRef.current && !comboRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const filteredSpeakers = searchQuery.trim()
    ? speakers.filter((s) => s.name.toLowerCase().includes(searchQuery.toLowerCase()))
    : speakers;

  const exactMatch = name.trim()
    ? speakers.find((s) => s.name.toLowerCase() === name.trim().toLowerCase())
    : undefined;

  function selectExistingSpeaker(s: Speaker) {
    setName(s.name);
    setSelectedSpeakerId(s.id);
    setDropdownOpen(false);
    setSearchQuery("");
  }

  function selectNewSpeaker(n: string) {
    setName(n.trim());
    setSelectedSpeakerId(null);
    setDropdownOpen(false);
    setSearchQuery("");
  }

  function clearSpeaker() {
    setName("");
    setSelectedSpeakerId(null);
    setSearchQuery("");
    setTimeout(() => setDropdownOpen(true), 50);
  }

  function handleFilesSelected(files: File[]) {
    setQueue((prev) => {
      const existingKeys = new Set(prev.map((q) => q.key));
      const newItems: QueuedFile[] = files
        .filter((f) => !existingKeys.has(f.name + f.size))
        .map((f) => ({ key: f.name + f.size, file: f, status: "pending" }));
      return [...prev, ...newItems];
    });
  }

  function removeFile(key: string) {
    setQueue((prev) => prev.filter((q) => q.key !== key));
  }

  const pendingCount = queue.filter((q) => q.status === "pending").length;
  const canEnroll = !!name.trim() && pendingCount > 0 && !isRunning;
  const allDone = queue.length > 0 && queue.every((q) => q.status === "done");

  async function startRun(overrideId?: number | null) {
    setIsRunning(true);
    let resolvedId: number | null = overrideId !== undefined ? overrideId : selectedSpeakerId;

    for (const item of queue) {
      if (item.status !== "pending") continue;
      setQueue((prev) =>
        prev.map((q) => (q.key === item.key ? { ...q, status: "uploading" } : q))
      );

      const form = new FormData();
      form.append("audio", item.file);
      form.append("speaker_name", name.trim());
      if (resolvedId !== null) form.append("speaker_id", String(resolvedId));

      try {
        const res = await fetch("/api/enroll", { method: "POST", body: form });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(err.detail ?? "Enrollment failed");
        }
        const data = await res.json();
        if (resolvedId === null) resolvedId = data.speaker_id;
        setQueue((prev) =>
          prev.map((q) =>
            q.key === item.key
              ? { ...q, status: "done", message: `#${data.embedding_id}` }
              : q
          )
        );
      } catch (e: unknown) {
        setQueue((prev) =>
          prev.map((q) =>
            q.key === item.key
              ? {
                  ...q,
                  status: "error",
                  message: e instanceof Error ? e.message : tCommon("unknown_error"),
                }
              : q
          )
        );
      }
    }

    fetch("/api/speakers")
      .then((r) => r.json())
      .then((d) => setSpeakers(d.speakers ?? []))
      .catch(() => {});
    setIsRunning(false);
  }

  async function handleEnroll() {
    if (!canEnroll) return;
    if (!selectedSpeakerId && exactMatch) {
      setDupDialogSpeaker(exactMatch);
      return;
    }
    await startRun();
  }

  function resetDone() {
    setQueue([]);
    setName("");
    setSelectedSpeakerId(null);
  }

  const hasSpeaker = !!(name && !dropdownOpen);

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      {/* Header */}
      <div className="animate-[fade-up_0.3s_ease-out_both]">
        <h1 className="text-2xl font-bold">{t("title")}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t("subtitle")}</p>
      </div>

      {/* ── Step 1: Select or create speaker ─────── */}
      <div className="rounded-2xl border border-border bg-card p-5 shadow-sm space-y-3 animate-[fade-up_0.3s_ease-out_both] relative z-10" style={{ animationDelay: "40ms" }}>
        <div className="flex items-center gap-2.5">
          <span className="inline-flex items-center justify-center size-6 rounded-full bg-primary text-primary-foreground text-xs font-bold shrink-0">
            1
          </span>
          <span className="text-sm font-semibold">{t("step_speaker")}</span>
        </div>

        <div ref={comboRef} className="relative">
          {hasSpeaker ? (
            /* Selected speaker pill */
            <div
              className={cn(
                "flex items-center gap-3 px-3.5 py-2.5 rounded-xl border",
                selectedSpeakerId !== null
                  ? "border-primary/40 bg-primary/10"
                  : "border-border bg-muted/40"
              )}
            >
              {selectedSpeakerId !== null ? (
                <Users className="size-4 text-primary shrink-0" />
              ) : (
                <UserPlus className="size-4 text-muted-foreground shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{name}</p>
                {selectedSpeakerId !== null && (
                  <p className="text-xs text-muted-foreground">
                    ID {selectedSpeakerId} ·{" "}
                    {speakers.find((s) => s.id === selectedSpeakerId)?.embedding_count ?? "?"}{" "}
                    {t("samples")}
                  </p>
                )}
              </div>
              <button
                onClick={clearSpeaker}
                className="p-1.5 -mr-0.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                aria-label={t("clear_speaker")}
              >
                <X className="size-3.5" />
              </button>
            </div>
          ) : (
            /* Search input */
            <div
              className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl border border-input bg-background cursor-text"
              onClick={() => { if (!dropdownOpen) setDropdownOpen(true); }}
            >
              <SearchIcon className="size-4 text-muted-foreground shrink-0" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => { setSearchQuery(e.target.value); setDropdownOpen(true); }}
                onFocus={() => setDropdownOpen(true)}
                onKeyDown={(e) => { if (e.key === "Escape") setDropdownOpen(false); }}
                placeholder={t("name_placeholder")}
                className="flex-1 text-sm bg-transparent outline-none placeholder:text-muted-foreground min-w-0"
              />
              <ChevronDown
                className={cn(
                  "size-4 text-muted-foreground transition-transform duration-150 shrink-0",
                  dropdownOpen && "rotate-180"
                )}
              />
            </div>
          )}

          {/* Dropdown */}
          {dropdownOpen && !hasSpeaker && (
            <div className="absolute z-20 top-full mt-1.5 w-full rounded-xl border border-border bg-card shadow-xl overflow-hidden">
              <div className="max-h-56 overflow-y-auto overscroll-contain">
                {filteredSpeakers.length > 0 && (
                  <p className="px-3.5 pt-2.5 pb-1 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                    {t("existing_speakers")}
                  </p>
                )}
                {filteredSpeakers.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => selectExistingSpeaker(s)}
                    className="w-full flex items-center gap-3 px-3.5 py-2.5 text-left hover:bg-accent transition-colors"
                  >
                    <Users className="size-3.5 text-muted-foreground shrink-0" />
                    <span className="flex-1 text-sm truncate">{s.name}</span>
                    <span className="text-xs text-muted-foreground tabular-nums shrink-0">
                      {s.embedding_count} {t("samples")}
                    </span>
                  </button>
                ))}
                {searchQuery.trim() && (
                  <button
                    onClick={() => selectNewSpeaker(searchQuery)}
                    className="w-full flex items-center gap-3 px-3.5 py-2.5 text-left hover:bg-accent transition-colors border-t border-border"
                  >
                    <UserPlus className="size-3.5 text-primary shrink-0" />
                    <span className="text-sm text-primary font-medium">
                      {t("create_new_speaker", { name: searchQuery.trim() })}
                    </span>
                  </button>
                )}
                {filteredSpeakers.length === 0 && !searchQuery.trim() && (
                  <p className="px-3.5 py-5 text-sm text-center text-muted-foreground">
                    {t("no_speakers_yet")}
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Step 2: Upload files ───────────────────── */}
      <div className="rounded-2xl border border-border bg-card p-5 shadow-sm space-y-3 animate-[fade-up_0.3s_ease-out_both]" style={{ animationDelay: "80ms" }}>
        <div className="flex items-center gap-2.5">
          <span className="inline-flex items-center justify-center size-6 rounded-full bg-primary text-primary-foreground text-xs font-bold shrink-0">
            2
          </span>
          <span className="text-sm font-semibold">{t("step_files")}</span>
        </div>

        <AudioUploader
          id="enroll-audio"
          label={t("audio_label")}
          multiple
          onFiles={handleFilesSelected}
        />

        {/* File queue */}
        {queue.length > 0 && (
          <div className="space-y-1.5">
            {queue.map((item) => (
              <div
                key={item.key}
                className={cn(
                  "flex items-center gap-3 px-3.5 py-2 rounded-xl border text-sm transition-colors",
                  item.status === "done" && "border-success/30 bg-success/10",
                  item.status === "error" && "border-destructive/30 bg-destructive/10",
                  item.status === "uploading" && "border-primary/30 bg-primary/10",
                  item.status === "pending" && "border-border bg-background/60"
                )}
              >
                <span className="shrink-0">
                  {item.status === "pending" && (
                    <span className="block size-4 rounded-full border-2 border-muted-foreground" />
                  )}
                  {item.status === "uploading" && (
                    <Loader2 className="size-4 animate-spin text-primary" />
                  )}
                  {item.status === "done" && <CheckCircle2 className="size-4 text-success" />}
                  {item.status === "error" && <XCircle className="size-4 text-destructive" />}
                </span>
                <span
                  className={cn(
                    "flex-1 truncate",
                    item.status === "done" && "text-success",
                    item.status === "error" && "text-destructive"
                  )}
                >
                  {item.file.name}
                </span>
                {item.message && (
                  <span className="text-xs text-muted-foreground shrink-0">{item.message}</span>
                )}
                {!isRunning && item.status !== "uploading" && (
                  <button
                    onClick={() => removeFile(item.key)}
                    className="shrink-0 p-1.5 -m-1.5 rounded-lg text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    aria-label={t("remove_file")}
                  >
                    <X className="size-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Actions ───────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3 animate-[fade-up_0.3s_ease-out_both]" style={{ animationDelay: "120ms" }}>
        <Button
          onClick={handleEnroll}
          disabled={!canEnroll}
          size="lg"
          className="flex-1 sm:flex-none"
        >
          {isRunning ? (
            <>
              <Loader2 className="mr-2 size-4 animate-spin" />
              {t("enrolling")}
            </>
          ) : (
            t("enroll_n", { count: pendingCount || queue.length })
          )}
        </Button>
        {allDone && (
          <Button variant="outline" size="lg" onClick={resetDone}>
            {t("enroll_another")}
          </Button>
        )}
        <span className="flex items-center gap-1.5 text-sm text-muted-foreground select-none ml-auto" title={tCommon("auto_preprocess_hint")}>
          <span className="inline-block size-2 rounded-full bg-primary" />
          {tCommon("auto_preprocess_label")}
        </span>
      </div>

      {/* ── Duplicate speaker popup ────────────────── */}
      <Dialog
        open={!!dupDialogSpeaker}
        onClose={() => setDupDialogSpeaker(null)}
        title={t("dup_dialog_title")}
        description={t("dup_dialog_desc")}
      >
        {dupDialogSpeaker && (
          <div className="space-y-4">
            <div className="rounded-xl border border-border bg-muted/40 px-4 py-3">
              <p className="text-sm font-semibold">{dupDialogSpeaker.name}</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                ID {dupDialogSpeaker.id} · {dupDialogSpeaker.embedding_count} {t("samples")}
              </p>
            </div>
            <div className="grid gap-2">
              <Button
                className="w-full"
                onClick={() => {
                  const s = dupDialogSpeaker;
                  setDupDialogSpeaker(null);
                  setSelectedSpeakerId(s.id);
                  startRun(s.id);
                }}
              >
                {t("add_to_existing")}
              </Button>
              <Button
                variant="outline"
                className="w-full"
                onClick={() => {
                  setDupDialogSpeaker(null);
                  setSelectedSpeakerId(null);
                  startRun(null);
                }}
              >
                {t("create_new_anyway")}
              </Button>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
}

