"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { ChevronDown, Database, Loader2, Search, Upload, Users, X } from "lucide-react";
import { AudioUploader } from "@/components/AudioUploader";
import { useBackgroundTasks, type Speaker, type VerifyResult } from "@/components/background-tasks";
import { ModelSelector } from "@/components/ModelSelector";
import { PreprocessControls } from "@/components/PreprocessControls";
import { ProcessingInsights } from "@/components/ProcessingInsights";
import { ResultCard } from "@/components/ResultCard";
import { VoiceProfileComparison } from "@/components/VoiceProfileComparison";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

type VerifyMode = "audio" | "database";

export default function VerifyPage() {
  const t = useTranslations("verify");
  const tPreprocess = useTranslations("preprocess");
  const tCommon = useTranslations("common");
  const { verify } = useBackgroundTasks();
  const {
    fileA,
    fileB,
    loading,
    result,
    error,
    uploadProgress,
    jobState,
    model,
    separateVocals,
    setFileA,
    setFileB,
    clearFileA,
    clearFileB,
    setModel,
    setSeparateVocals,
    start,
  } = verify;
  const [mode, setMode] = useState<VerifyMode>("audio");
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [speakersLoading, setSpeakersLoading] = useState(false);
  const [speakerAId, setSpeakerAId] = useState("");
  const [speakerBId, setSpeakerBId] = useState("");
  const [databaseLoading, setDatabaseLoading] = useState(false);
  const [databaseResult, setDatabaseResult] = useState<VerifyResult | null>(null);
  const [databaseError, setDatabaseError] = useState<string | null>(null);

  useEffect(() => {
    setSpeakersLoading(true);
    fetch("/api/speakers", { cache: "no-store" })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail ?? tCommon("unknown_error"));
        setSpeakers((data.speakers ?? []).filter((speaker: Speaker) => speaker.embedding_count > 0));
      })
      .catch((fetchError: unknown) => {
        setDatabaseError(fetchError instanceof Error ? fetchError.message : tCommon("unknown_error"));
      })
      .finally(() => setSpeakersLoading(false));
  }, [tCommon]);

  const selectedSpeakerA = useMemo(
    () => speakers.find((speaker) => String(speaker.id) === speakerAId),
    [speakerAId, speakers],
  );
  const selectedSpeakerB = useMemo(
    () => speakers.find((speaker) => String(speaker.id) === speakerBId),
    [speakerBId, speakers],
  );
  const activeLoading = mode === "audio" ? loading : databaseLoading;
  const activeResult = mode === "audio" ? result : databaseResult;
  const activeError = mode === "audio" ? error : databaseError;

  function changeMode(nextMode: VerifyMode) {
    setMode(nextMode);
    setDatabaseError(null);
  }

  async function compareEnrolledSpeakers() {
    if (!speakerAId || !speakerBId || speakerAId === speakerBId || databaseLoading) return;
    setDatabaseLoading(true);
    setDatabaseResult(null);
    setDatabaseError(null);
    try {
      const response = await fetch("/api/verify/speakers", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          speaker_a_id: Number(speakerAId),
          speaker_b_id: Number(speakerBId),
          model,
        }),
      });
      const data = await response.json().catch(() => ({ detail: tCommon("unknown_error") }));
      if (!response.ok) throw new Error(data.detail ?? tCommon("unknown_error"));
      setDatabaseResult(data as VerifyResult);
    } catch (compareError: unknown) {
      setDatabaseError(compareError instanceof Error ? compareError.message : tCommon("unknown_error"));
    } finally {
      setDatabaseLoading(false);
    }
  }

  function changeSpeakerA(value: string) {
    setSpeakerAId(value);
    setDatabaseResult(null);
    setDatabaseError(null);
  }

  function changeSpeakerB(value: string) {
    setSpeakerBId(value);
    setDatabaseResult(null);
    setDatabaseError(null);
  }

  function getStageLabel(stage: string | undefined): string {
    switch (stage) {
      case "queued": return t("stage_queued");
      case "download": return t("stage_download");
      case "preprocess_a": return t("stage_preprocess_a");
      case "embed_a": return t("stage_embed_a");
      case "preprocess_b": return t("stage_preprocess_b");
      case "embed_b": return t("stage_embed_b");
      case "speaker_lookup": return t("stage_speaker_lookup");
      case "score": return t("stage_score");
      case "done": return t("stage_done");
      case "failed": return t("stage_failed");
      default: return t("stage_running");
    }
  }

  return (
    <div className="space-y-8">
      <div className="animate-[fade-up_0.3s_ease-out_both]">
        <h1 className="text-2xl font-bold">{t("title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      <div className="inline-flex rounded-md border bg-muted p-1" role="tablist" aria-label={t("mode_label")}>
        {(["audio", "database"] as const).map((item) => (
          <button
            key={item}
            type="button"
            role="tab"
            aria-selected={mode === item}
            onClick={() => changeMode(item)}
            className={cn(
              "inline-flex h-9 items-center gap-2 rounded px-3 text-sm font-medium transition-colors",
              mode === item ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {item === "audio" ? <Upload /> : <Database />}
            {t(item === "audio" ? "mode_audio" : "mode_database")}
          </button>
        ))}
      </div>

      <ModelSelector value={model} onChange={setModel} />

      {mode === "audio" ? (
        <>
          <PreprocessControls
            separateVocals={separateVocals}
            onSeparateVocalsChange={setSeparateVocals}
            fixedNote={tPreprocess("locked_verify_note")}
          />
          <div className="grid gap-6 sm:grid-cols-2">
            <AudioUploader id="audio-a" label={t("audio_a")} files={fileA ? [fileA] : []} uploading={loading} onFile={setFileA} onClear={clearFileA} />
            <AudioUploader id="audio-b" label={t("audio_b")} files={fileB ? [fileB] : []} uploading={loading} onFile={setFileB} onClear={clearFileB} />
          </div>
          <Button onClick={() => void start()} disabled={!fileA || !fileB || loading} size="lg" className="w-full sm:w-auto">
            {loading && <Loader2 className="animate-spin" />}
            {loading ? t("comparing") : t("compare")}
          </Button>
        </>
      ) : (
        <div className="space-y-5">
          <p className="text-sm text-muted-foreground">{t("database_hint")}</p>
          <div className="grid gap-6 sm:grid-cols-2">
            <SpeakerSelect label={t("speaker_a")} value={speakerAId} onChange={changeSpeakerA} speakers={speakers} excludedId={speakerBId} loading={speakersLoading} />
            <SpeakerSelect label={t("speaker_b")} value={speakerBId} onChange={changeSpeakerB} speakers={speakers} excludedId={speakerAId} loading={speakersLoading} />
          </div>
          {!speakersLoading && speakers.length < 2 && <p className="text-sm text-muted-foreground">{t("not_enough_speakers")}</p>}
          <Button onClick={() => void compareEnrolledSpeakers()} disabled={!speakerAId || !speakerBId || speakerAId === speakerBId || databaseLoading} size="lg" className="w-full sm:w-auto">
            {databaseLoading && <Loader2 className="animate-spin" />}
            {databaseLoading ? t("comparing") : t("compare_database")}
          </Button>
        </div>
      )}

      {mode === "audio" && loading && (
        <div className="space-y-4 rounded-lg border bg-card p-4">
          <div><div className="flex justify-between text-xs text-muted-foreground"><span>{t("upload_progress")}</span><span>{Math.round(uploadProgress)}%</span></div><Progress value={uploadProgress} className="mt-2 h-2" /></div>
          <div><div className="flex justify-between text-xs text-muted-foreground"><span>{t("processing_progress")}</span><span>{jobState ? `${Math.round(jobState.progress)}%` : t("queueing")}</span></div><Progress value={jobState?.progress ?? 0} className="mt-2 h-2" /><p className="mt-2 text-xs text-muted-foreground">{t("current_stage")} {getStageLabel(jobState?.stage)}</p></div>
        </div>
      )}

      {activeError && <p className="text-sm text-destructive">{activeError}</p>}
      {activeResult && !activeLoading && (
        <div className="space-y-2">
          {mode === "database" && selectedSpeakerA && selectedSpeakerB && <p className="text-sm font-medium">{t("comparison_pair", { speakerA: selectedSpeakerA.name, speakerB: selectedSpeakerB.name })}</p>}
          <ResultCard
            score={activeResult.score}
            decision={activeResult.decision}
            isSameSpeaker={activeResult.is_same_speaker}
            sameThreshold={activeResult.same_threshold ?? activeResult.threshold}
            differentThreshold={activeResult.different_threshold}
          />
          {mode === "database" && activeResult.profile_scores && (
            <div className="grid gap-2 rounded-md border bg-card p-3 text-sm sm:grid-cols-3">
              <p>
                <span className="text-muted-foreground">{t("profile_coverage_score")}: </span>
                <strong className="tabular-nums">{activeResult.profile_scores.coverage.toFixed(4)}</strong>
              </p>
              <p>
                <span className="text-muted-foreground">{t("profile_centroid_score")}: </span>
                <strong className="tabular-nums">{activeResult.profile_scores.centroid.toFixed(4)}</strong>
              </p>
              <p>
                <span className="text-muted-foreground">{t("profile_asset_counts")}: </span>
                <strong className="tabular-nums">
                  {activeResult.profile_scores.asset_count_a} / {activeResult.profile_scores.asset_count_b}
                </strong>
              </p>
              <p className="text-xs text-muted-foreground sm:col-span-3">
                {t("profile_score_explanation")}
              </p>
            </div>
          )}
          <ProcessingInsights mode="verify" strategy={activeResult.strategy} elapsedSeconds={activeResult.elapsed_seconds} />
          {activeResult.strategy === "full" &&
            activeResult.preprocess_options?.separation_requested &&
            !activeResult.preprocess_options.separate_vocals && (
              <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                {tPreprocess("separation_failed_warning")}
              </p>
            )}
          {mode === "audio" && <VoiceProfileComparison profile={activeResult.voice_characteristics ?? null} />}
          {activeResult.model_used && <p className="text-xs text-muted-foreground">Model: {activeResult.model_used}</p>}
        </div>
      )}
    </div>
  );
}

function SpeakerSelect({ label, value, onChange, speakers, excludedId, loading }: { label: string; value: string; onChange: (value: string) => void; speakers: Speaker[]; excludedId: string; loading: boolean }) {
  const t = useTranslations("verify");
  const inputId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const selectedSpeaker = speakers.find((speaker) => String(speaker.id) === value) ?? null;
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const filteredSpeakers = speakers.filter((speaker) => {
    if (String(speaker.id) === excludedId) return false;
    if (!normalizedQuery) return true;
    return speaker.name.toLocaleLowerCase().includes(normalizedQuery) || String(speaker.id).includes(normalizedQuery);
  });

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function selectSpeaker(speaker: Speaker) {
    onChange(String(speaker.id));
    setQuery("");
    setOpen(false);
  }

  function clearSpeaker() {
    onChange("");
    setQuery("");
    setOpen(true);
  }

  return (
    <div ref={rootRef} className="relative space-y-2">
      <label htmlFor={inputId} className="text-sm font-medium">{label}</label>
      {selectedSpeaker ? (
        <div className="flex h-11 items-center gap-3 rounded-md border border-primary/40 bg-primary/10 px-3">
          <Users className="size-4 shrink-0 text-primary" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{selectedSpeaker.name}</p>
            <p className="text-xs text-muted-foreground">ID {selectedSpeaker.id}</p>
          </div>
          <button type="button" onClick={clearSpeaker} className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground" aria-label={t("clear_speaker", { label })}>
            <X className="size-4" />
          </button>
        </div>
      ) : (
        <div className="flex h-11 items-center gap-2.5 rounded-md border border-input bg-background px-3 focus-within:ring-2 focus-within:ring-ring">
          {loading ? <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" /> : <Search className="size-4 shrink-0 text-muted-foreground" />}
          <input
            id={inputId}
            type="search"
            value={query}
            disabled={loading}
            onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
            onFocus={() => setOpen(true)}
            onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }}
            placeholder={loading ? t("loading_speakers") : t("search_speaker")}
            autoComplete="off"
            className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          <ChevronDown className={cn("size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
        </div>
      )}

      {open && !selectedSpeaker && !loading && (
        <div className="absolute top-full z-20 mt-1.5 max-h-60 w-full overflow-y-auto rounded-md border border-border bg-card py-1 shadow-xl overscroll-contain">
          {filteredSpeakers.map((speaker) => (
            <button key={speaker.id} type="button" onClick={() => selectSpeaker(speaker)} className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-accent">
              <Users className="size-4 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate text-sm">{speaker.name}</span>
              <span className="shrink-0 text-xs tabular-nums text-muted-foreground">ID {speaker.id}</span>
            </button>
          ))}
          {filteredSpeakers.length === 0 && <p className="px-3 py-5 text-center text-sm text-muted-foreground">{t("no_matching_speakers")}</p>}
        </div>
      )}
    </div>
  );
}
