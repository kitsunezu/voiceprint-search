"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Database, Loader2, Upload } from "lucide-react";
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
            <SpeakerSelect label={t("speaker_a")} value={speakerAId} onChange={setSpeakerAId} speakers={speakers} excludedId={speakerBId} placeholder={speakersLoading ? t("loading_speakers") : t("select_speaker")} />
            <SpeakerSelect label={t("speaker_b")} value={speakerBId} onChange={setSpeakerBId} speakers={speakers} excludedId={speakerAId} placeholder={speakersLoading ? t("loading_speakers") : t("select_speaker")} />
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
          <ResultCard score={activeResult.score} probability={activeResult.probability} isSameSpeaker={activeResult.is_same_speaker} />
          <ProcessingInsights mode="verify" strategy={activeResult.strategy} elapsedSeconds={activeResult.elapsed_seconds} />
          {mode === "audio" && <VoiceProfileComparison profile={activeResult.voice_characteristics ?? null} />}
          {activeResult.model_used && <p className="text-xs text-muted-foreground">Model: {activeResult.model_used}</p>}
        </div>
      )}
    </div>
  );
}

function SpeakerSelect({ label, value, onChange, speakers, excludedId, placeholder }: { label: string; value: string; onChange: (value: string) => void; speakers: Speaker[]; excludedId: string; placeholder: string }) {
  return (
    <label className="space-y-2">
      <span className="text-sm font-medium">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} className="h-11 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <option value="">{placeholder}</option>
        {speakers.filter((speaker) => String(speaker.id) !== excludedId).map((speaker) => <option key={speaker.id} value={speaker.id}>{speaker.name} (ID: {speaker.id})</option>)}
      </select>
    </label>
  );
}
