"use client";

import { useTranslations } from "next-intl";
import { Loader2 } from "lucide-react";
import { AudioUploader } from "@/components/AudioUploader";
import { useBackgroundTasks } from "@/components/background-tasks";
import { ModelSelector } from "@/components/ModelSelector";
import { PreprocessControls } from "@/components/PreprocessControls";
import { ProcessingInsights } from "@/components/ProcessingInsights";
import { ResultCard } from "@/components/ResultCard";
import { VoiceProfileComparison } from "@/components/VoiceProfileComparison";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

export default function VerifyPage() {
  const t = useTranslations("verify");
  const tPreprocess = useTranslations("preprocess");
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

  function getStageLabel(stage: string | undefined): string {
    switch (stage) {
      case "queued":
        return t("stage_queued");
      case "download":
        return t("stage_download");
      case "preprocess_a":
        return t("stage_preprocess_a");
      case "embed_a":
        return t("stage_embed_a");
      case "preprocess_b":
        return t("stage_preprocess_b");
      case "embed_b":
        return t("stage_embed_b");
      case "speaker_lookup":
        return t("stage_speaker_lookup");
      case "score":
        return t("stage_score");
      case "done":
        return t("stage_done");
      case "failed":
        return t("stage_failed");
      default:
        return t("stage_running");
    }
  }

  return (
    <div className="space-y-8">
      <div className="animate-[fade-up_0.3s_ease-out_both]">
        <h1 className="text-2xl font-bold">{t("title")}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t("subtitle")}</p>
      </div>

      {/* Model selector */}
      <div className="animate-[fade-up_0.3s_ease-out_both]" style={{ animationDelay: "40ms" }}>
        <ModelSelector value={model} onChange={setModel} />
      </div>

      <div className="animate-[fade-up_0.3s_ease-out_both]" style={{ animationDelay: "55ms" }}>
        <PreprocessControls
          separateVocals={separateVocals}
          onSeparateVocalsChange={setSeparateVocals}
          fixedNote={tPreprocess("locked_verify_note")}
        />
      </div>

      <div className="grid gap-6 sm:grid-cols-2 animate-[fade-up_0.3s_ease-out_both]" style={{ animationDelay: "70ms" }}>
        <AudioUploader
          id="audio-a"
          label={t("audio_a")}
          files={fileA ? [fileA] : []}
          uploading={loading}
          onFile={setFileA}
          onClear={clearFileA}
        />
        <AudioUploader
          id="audio-b"
          label={t("audio_b")}
          files={fileB ? [fileB] : []}
          uploading={loading}
          onFile={setFileB}
          onClear={clearFileB}
        />
      </div>

      <div className="animate-[fade-up_0.3s_ease-out_both]" style={{ animationDelay: "120ms" }}>
        <Button
          onClick={() => {
            void start();
          }}
          disabled={!fileA || !fileB || loading}
          size="lg"
          className="w-full sm:w-auto"
        >
          {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {loading ? t("comparing") : t("compare")}
        </Button>
      </div>

      {loading && (
        <div className="rounded-xl border bg-card p-4 space-y-4 animate-[fade-up_0.25s_ease-out_both]">
          <div>
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{t("upload_progress")}</span>
              <span>{Math.round(uploadProgress)}%</span>
            </div>
            <Progress value={uploadProgress} className="mt-2 h-2" />
          </div>

          <div>
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{t("processing_progress")}</span>
              <span>{jobState ? `${Math.round(jobState.progress)}%` : t("queueing")}</span>
            </div>
            <Progress value={jobState?.progress ?? 0} className="mt-2 h-2" />
            <p className="text-xs text-muted-foreground mt-2">
              {t("current_stage")} {getStageLabel(jobState?.stage)}
            </p>
            {typeof jobState?.eta_seconds === "number" && jobState.eta_seconds > 0 && (
              <p className="text-xs text-muted-foreground mt-1">
                {t("eta_seconds", { seconds: jobState.eta_seconds })}
              </p>
            )}
          </div>
        </div>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}
      {result && (
        <div className="space-y-2">
          <ResultCard
            score={result.score}
            probability={result.probability}
            isSameSpeaker={result.is_same_speaker}
          />
          <ProcessingInsights
            mode="verify"
            strategy={result.strategy}
            elapsedSeconds={result.elapsed_seconds}
          />
          <VoiceProfileComparison profile={result.voice_characteristics ?? null} />
          {result.model_used && (
            <p className="text-xs text-muted-foreground">
              Model: {result.model_used}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
