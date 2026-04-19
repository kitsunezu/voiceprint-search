"use client";

import { useTranslations } from "next-intl";
import { Loader2, Music2 } from "lucide-react";
import { AudioUploader } from "@/components/AudioUploader";
import { useBackgroundTasks } from "@/components/background-tasks";
import { ModelSelector } from "@/components/ModelSelector";
import { PreprocessControls } from "@/components/PreprocessControls";
import { ProcessingInsights } from "@/components/ProcessingInsights";
import { ResultCard } from "@/components/ResultCard";
import { Button } from "@/components/ui/button";

export default function SearchPage() {
  const t = useTranslations("search");
  const tPreprocess = useTranslations("preprocess");
  const { search } = useBackgroundTasks();
  const {
    file,
    loading,
    results,
    error,
    model,
    limit,
    modelUsed,
    separateVocals,
    elapsedSeconds,
    setFile,
    setModel,
    setLimit,
    setSeparateVocals,
    clear,
    start,
  } = search;

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
          fixedNote={tPreprocess("locked_search_note")}
        />
      </div>

      <div className="animate-[fade-up_0.3s_ease-out_both]" style={{ animationDelay: "60ms" }}>
        <AudioUploader
          id="audio-query"
          label={t("query_label")}
          files={file ? [file] : []}
          onFile={setFile}
          onClear={clear}
        />
      </div>

      {/* Search controls row */}
      <div
        className="flex flex-wrap items-center gap-4 animate-[fade-up_0.3s_ease-out_both]"
        style={{ animationDelay: "120ms" }}
      >
        <Button
          onClick={() => {
            void start();
          }}
          disabled={!file || loading}
          size="lg"
          className="w-full sm:w-auto"
        >
          {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {loading ? t("searching") : t("search")}
        </Button>

        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          {t("limit_label")}
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="rounded-md border border-border bg-card px-2 py-1 text-sm"
          >
            {[5, 10, 20, 50].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
      </div>

      {error && (
        <p className="text-sm text-destructive animate-[fade-up_0.25s_ease-out_both]">{error}</p>
      )}

      {results.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 animate-[fade-up_0.25s_ease-out_both]">
            <h2 className="font-semibold">{t("results")}</h2>
            {modelUsed && (
              <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                {modelUsed}
              </span>
            )}
          </div>
          {results.map((m, i) => (
            <div
              key={m.speaker_id}
              className="space-y-2 animate-[fade-up_0.35s_ease-out_both]"
              style={{ animationDelay: `${i * 80}ms` }}
            >
              <ResultCard
                score={m.score}
                probability={m.probability}
                speakerName={m.speaker_name}
                rank={m.rank}
              />
              {/* ── Per-speaker audio sample ── */}
              <div className="rounded-xl border border-border bg-card px-4 py-3 flex items-center gap-3">
                <Music2 className="h-4 w-4 text-primary shrink-0" />
                <span className="text-xs text-muted-foreground whitespace-nowrap">
                  {t("sample_audio")}
                </span>
                {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                <audio
                  controls
                  src={`/api/speakers/${m.speaker_id}/audio`}
                  className="flex-1 h-8 min-w-0"
                  preload="metadata"
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {elapsedSeconds != null && <ProcessingInsights mode="search" elapsedSeconds={elapsedSeconds} />}

      {results.length === 0 && !loading && !error && file && (
        <p className="text-sm text-muted-foreground">{t("no_results")}</p>
      )}
    </div>
  );
}

