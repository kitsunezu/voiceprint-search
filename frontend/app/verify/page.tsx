"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2 } from "lucide-react";
import { AudioUploader } from "@/components/AudioUploader";
import { ModelSelector } from "@/components/ModelSelector";
import { PreprocessControls } from "@/components/PreprocessControls";
import { ProcessingInsights } from "@/components/ProcessingInsights";
import { ResultCard } from "@/components/ResultCard";
import { VoiceProfileComparison } from "@/components/VoiceProfileComparison";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

const VERIFY_TOTAL_UPLOAD_LIMIT_BYTES = 50 * 1024 * 1024;
const VERIFY_TOTAL_UPLOAD_LIMIT_MB = Math.floor(VERIFY_TOTAL_UPLOAD_LIMIT_BYTES / (1024 * 1024));
const VERIFY_JOB_POLL_INTERVAL_MS = 1000;
const VERIFY_JOB_MAX_POLLS = 900;

interface VoiceDimension {
  key: string;
  audio_a: number;
  audio_b: number;
  difference: number;
  audio_a_value: number;
  audio_b_value: number;
  unit: string;
}

interface VoiceCharacteristics {
  profile_similarity: number;
  summary: string;
  dimensions: VoiceDimension[];
}

interface VerifyResult {
  score: number;
  probability: number;
  is_same_speaker: boolean;
  threshold: number;
  elapsed_seconds?: number;
  model_used?: string;
  strategy?: string;
  voice_characteristics?: VoiceCharacteristics;
}

interface VerifyJobState {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  stage: string;
  progress: number;
  eta_seconds: number | null;
  error?: string | null;
  result?: VerifyResult;
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export default function VerifyPage() {
  const t = useTranslations("verify");
  const tCommon = useTranslations("common");
  const tPreprocess = useTranslations("preprocess");
  const [fileA, setFileA] = useState<File | null>(null);
  const [fileB, setFileB] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [jobState, setJobState] = useState<VerifyJobState | null>(null);
  const [model, setModel] = useState("");
  const [separateVocals, setSeparateVocals] = useState(true);

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

  async function createVerifyJob(formData: FormData): Promise<VerifyJobState> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/verify/jobs");
      xhr.responseType = "json";

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && event.total > 0) {
          const percent = (event.loaded / event.total) * 100;
          setUploadProgress(Math.min(100, Math.max(0, percent)));
        }
      };

      xhr.onload = () => {
        const body =
          (xhr.response as Record<string, unknown> | null) ??
          (() => {
            try {
              return JSON.parse(xhr.responseText || "{}");
            } catch {
              return {};
            }
          })();

        if (xhr.status >= 200 && xhr.status < 300) {
          setUploadProgress(100);
          resolve(body as unknown as VerifyJobState);
          return;
        }

        const detail =
          typeof body?.detail === "string"
            ? body.detail
            : xhr.statusText || tCommon("unknown_error");
        reject(new Error(detail));
      };

      xhr.onerror = () => {
        reject(new Error(tCommon("unknown_error")));
      };

      xhr.send(formData);
    });
  }

  async function pollVerifyJob(jobId: string): Promise<VerifyJobState> {
    for (let attempt = 0; attempt < VERIFY_JOB_MAX_POLLS; attempt += 1) {
      const res = await fetch(`/api/verify/jobs/${jobId}`, {
        method: "GET",
        cache: "no-store",
      });
      const data =
        ((await res.json().catch(() => ({ detail: res.statusText }))) as VerifyJobState & {
          detail?: string;
        }) ?? null;

      if (!res.ok || !data) {
        throw new Error(data?.detail ?? tCommon("unknown_error"));
      }

      setJobState(data);

      if (data.status === "succeeded" || data.status === "failed") {
        return data;
      }

      await sleep(VERIFY_JOB_POLL_INTERVAL_MS);
    }

    throw new Error(t("job_timeout"));
  }

  async function handleSubmit() {
    if (!fileA || !fileB) return;

    const totalBytes = fileA.size + fileB.size;
    if (totalBytes > VERIFY_TOTAL_UPLOAD_LIMIT_BYTES) {
      setError(t("max_total_size_exceeded", { maxMB: VERIFY_TOTAL_UPLOAD_LIMIT_MB }));
      setResult(null);
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);
    setUploadProgress(0);
    setJobState(null);

    const form = new FormData();
    form.append("audio_a", fileA);
    form.append("audio_b", fileB);
    form.append("separate_vocals", String(separateVocals));
    form.append("denoise", "true");
    form.append("enable_fast_return", "true");
    if (model) form.append("model", model);

    try {
      const created = await createVerifyJob(form);
      setJobState(created);

      const finished = await pollVerifyJob(created.job_id);
      if (finished.status === "failed") {
        throw new Error(finished.error ?? t("job_failed"));
      }
      if (!finished.result) {
        throw new Error(t("job_missing_result"));
      }

      setResult(finished.result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tCommon("unknown_error"));
    } finally {
      setLoading(false);
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
          uploading={loading}
          onFile={setFileA}
          onClear={() => { setFileA(null); setResult(null); setError(null); }}
        />
        <AudioUploader
          id="audio-b"
          label={t("audio_b")}
          uploading={loading}
          onFile={setFileB}
          onClear={() => { setFileB(null); setResult(null); setError(null); }}
        />
      </div>

      <div className="animate-[fade-up_0.3s_ease-out_both]" style={{ animationDelay: "120ms" }}>
        <Button
          onClick={handleSubmit}
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
