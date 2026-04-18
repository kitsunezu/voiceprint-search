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

export default function VerifyPage() {
  const t = useTranslations("verify");
  const tCommon = useTranslations("common");
  const tPreprocess = useTranslations("preprocess");
  const [fileA, setFileA] = useState<File | null>(null);
  const [fileB, setFileB] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [model, setModel] = useState("");
  const [separateVocals, setSeparateVocals] = useState(true);

  async function handleSubmit() {
    if (!fileA || !fileB) return;
    setLoading(true);
    setError(null);
    setResult(null);

    const form = new FormData();
    form.append("audio_a", fileA);
    form.append("audio_b", fileB);
    form.append("separate_vocals", String(separateVocals));
    form.append("denoise", "true");
    form.append("enable_fast_return", "true");
    if (model) form.append("model", model);

    try {
      const res = await fetch("/api/verify", { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? "Verification failed");
      }
      setResult(await res.json());
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
          onFile={setFileA}
          onClear={() => { setFileA(null); setResult(null); setError(null); }}
        />
        <AudioUploader
          id="audio-b"
          label={t("audio_b")}
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
