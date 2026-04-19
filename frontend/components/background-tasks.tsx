"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

const VERIFY_TOTAL_UPLOAD_LIMIT_BYTES = 50 * 1024 * 1024;
const VERIFY_TOTAL_UPLOAD_LIMIT_MB = Math.floor(VERIFY_TOTAL_UPLOAD_LIMIT_BYTES / (1024 * 1024));
const VERIFY_JOB_POLL_INTERVAL_MS = 1000;
const VERIFY_JOB_MAX_POLLS = 900;

export interface SearchMatch {
  speaker_id: number;
  speaker_name: string;
  score: number;
  probability: number;
  rank: number;
}

interface SearchResponse {
  results: SearchMatch[];
  elapsed_seconds?: number;
  model_used?: string;
}

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

export interface VerifyResult {
  score: number;
  probability: number;
  is_same_speaker: boolean;
  threshold: number;
  elapsed_seconds?: number;
  model_used?: string;
  strategy?: string;
  voice_characteristics?: VoiceCharacteristics;
}

export interface VerifyJobState {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  stage: string;
  progress: number;
  eta_seconds: number | null;
  error?: string | null;
  result?: VerifyResult;
}

export type Speaker = {
  id: number;
  name: string;
  embedding_count: number;
  created_at: string;
};

export type FileStatus = "pending" | "uploading" | "queueing" | "done" | "error";

export type QueuedFile = {
  key: string;
  file: File;
  status: FileStatus;
  message?: string;
  uploadProgress?: number;
  jobId?: string;
};

type EnrollJobAccepted = { job_id?: string; speaker_id?: number };

interface EnrollJobResult {
  speaker_id: number;
  audio_asset_id: number;
  processing_queued?: boolean;
  message?: string;
}

interface EnrollJobState {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  stage: string;
  progress: number;
  eta_seconds: number | null;
  error?: string | null;
  result?: EnrollJobResult | null;
}

type StagedEnrollJob = { itemKey: string; jobId: string };

type CreatedSpeaker = {
  id: number;
  name: string;
  embedding_count: number;
  created_at: string;
};

type BackgroundTasksContextValue = {
  search: {
    file: File | null;
    loading: boolean;
    results: SearchMatch[];
    error: string | null;
    model: string;
    limit: number;
    modelUsed: string;
    separateVocals: boolean;
    elapsedSeconds: number | null;
    setFile: (file: File | null) => void;
    setModel: (model: string) => void;
    setLimit: (limit: number) => void;
    setSeparateVocals: (value: boolean) => void;
    clear: () => void;
    start: () => Promise<void>;
  };
  verify: {
    fileA: File | null;
    fileB: File | null;
    loading: boolean;
    result: VerifyResult | null;
    error: string | null;
    uploadProgress: number;
    jobState: VerifyJobState | null;
    model: string;
    separateVocals: boolean;
    setFileA: (file: File | null) => void;
    setFileB: (file: File | null) => void;
    clearFileA: () => void;
    clearFileB: () => void;
    setModel: (model: string) => void;
    setSeparateVocals: (value: boolean) => void;
    start: () => Promise<void>;
  };
  enroll: {
    name: string;
    queue: QueuedFile[];
    isRunning: boolean;
    speakers: Speaker[];
    selectedSpeakerId: number | null;
    dupDialogSpeaker: Speaker | null;
    dropdownOpen: boolean;
    searchQuery: string;
    filteredSpeakers: Speaker[];
    pendingCount: number;
    canEnroll: boolean;
    allDone: boolean;
    hasSpeaker: boolean;
    setName: (name: string) => void;
    setDropdownOpen: (open: boolean) => void;
    setSearchQuery: (query: string) => void;
    clearUploadedFiles: () => void;
    selectExistingSpeaker: (speaker: Speaker) => void;
    selectNewSpeaker: (name: string) => void;
    clearSpeaker: () => void;
    handleFilesSelected: (files: File[]) => void;
    removeFile: (key: string) => void;
    handleEnroll: () => Promise<void>;
    confirmDuplicateExisting: () => Promise<void>;
    confirmDuplicateNew: () => Promise<void>;
    closeDuplicateDialog: () => void;
    resetDone: () => void;
  };
};

const BackgroundTasksContext = createContext<BackgroundTasksContextValue | null>(null);

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function BackgroundTasksProvider({ children }: { children: React.ReactNode }) {
  const tEnroll = useTranslations("enroll");
  const tVerify = useTranslations("verify");
  const tCommon = useTranslations("common");

  const [searchFile, setSearchFile] = useState<File | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchMatch[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchModel, setSearchModel] = useState("");
  const [searchLimit, setSearchLimit] = useState(10);
  const [searchModelUsed, setSearchModelUsed] = useState("");
  const [searchSeparateVocals, setSearchSeparateVocals] = useState(true);
  const [searchElapsedSeconds, setSearchElapsedSeconds] = useState<number | null>(null);

  const [verifyFileA, setVerifyFileA] = useState<File | null>(null);
  const [verifyFileB, setVerifyFileB] = useState<File | null>(null);
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [verifyUploadProgress, setVerifyUploadProgress] = useState(0);
  const [verifyJobState, setVerifyJobState] = useState<VerifyJobState | null>(null);
  const [verifyModel, setVerifyModel] = useState("");
  const [verifySeparateVocals, setVerifySeparateVocals] = useState(true);

  const [enrollName, setEnrollName] = useState("");
  const [enrollQueue, setEnrollQueue] = useState<QueuedFile[]>([]);
  const [enrollIsRunning, setEnrollIsRunning] = useState(false);
  const [enrollSpeakers, setEnrollSpeakers] = useState<Speaker[]>([]);
  const [enrollSelectedSpeakerId, setEnrollSelectedSpeakerId] = useState<number | null>(null);
  const [enrollDupDialogSpeaker, setEnrollDupDialogSpeaker] = useState<Speaker | null>(null);
  const [enrollDropdownOpen, setEnrollDropdownOpen] = useState(false);
  const [enrollSearchQuery, setEnrollSearchQuery] = useState("");

  useEffect(() => {
    fetch("/api/speakers")
      .then((response) => response.json())
      .then((data: { speakers?: Speaker[] }) => setEnrollSpeakers(data.speakers ?? []))
      .catch(() => {});
  }, []);

  async function startSearch() {
    if (!searchFile || searchLoading) return;

    setSearchLoading(true);
    setSearchError(null);
    setSearchResults([]);
    setSearchModelUsed("");
    setSearchElapsedSeconds(null);

    const form = new FormData();
    form.append("audio", searchFile);
    form.append("limit", String(searchLimit));
    form.append("separate_vocals", String(searchSeparateVocals));
    form.append("denoise", "true");
    if (searchModel) form.append("model", searchModel);

    try {
      const response = await fetch("/api/search", { method: "POST", body: form });
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(err.detail ?? "Search failed");
      }

      const data: SearchResponse = await response.json();
      setSearchResults(data.results);
      setSearchModelUsed(data.model_used ?? "");
      setSearchElapsedSeconds(data.elapsed_seconds ?? null);
    } catch (error: unknown) {
      setSearchError(error instanceof Error ? error.message : tCommon("unknown_error"));
    } finally {
      setSearchLoading(false);
    }
  }

  function clearSearch() {
    setSearchFile(null);
    setSearchResults([]);
    setSearchError(null);
    setSearchModelUsed("");
    setSearchElapsedSeconds(null);
  }

  async function createVerifyJob(formData: FormData): Promise<VerifyJobState> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/verify/jobs");
      xhr.responseType = "json";

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && event.total > 0) {
          const percent = (event.loaded / event.total) * 100;
          setVerifyUploadProgress(Math.min(100, Math.max(0, percent)));
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
          setVerifyUploadProgress(100);
          resolve(body as VerifyJobState);
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
      const response = await fetch(`/api/verify/jobs/${jobId}`, {
        method: "GET",
        cache: "no-store",
      });
      const data =
        ((await response.json().catch(() => ({ detail: response.statusText }))) as VerifyJobState & {
          detail?: string;
        }) ?? null;

      if (!response.ok || !data) {
        throw new Error(data?.detail ?? tCommon("unknown_error"));
      }

      setVerifyJobState(data);

      if (data.status === "succeeded" || data.status === "failed") {
        return data;
      }

      await sleep(VERIFY_JOB_POLL_INTERVAL_MS);
    }

    throw new Error(tVerify("job_timeout"));
  }

  async function startVerify() {
    if (!verifyFileA || !verifyFileB || verifyLoading) return;

    const totalBytes = verifyFileA.size + verifyFileB.size;
    if (totalBytes > VERIFY_TOTAL_UPLOAD_LIMIT_BYTES) {
      setVerifyError(tVerify("max_total_size_exceeded", { maxMB: VERIFY_TOTAL_UPLOAD_LIMIT_MB }));
      setVerifyResult(null);
      return;
    }

    setVerifyLoading(true);
    setVerifyError(null);
    setVerifyResult(null);
    setVerifyUploadProgress(0);
    setVerifyJobState(null);

    const form = new FormData();
    form.append("audio_a", verifyFileA);
    form.append("audio_b", verifyFileB);
    form.append("separate_vocals", String(verifySeparateVocals));
    form.append("denoise", "true");
    form.append("enable_fast_return", "true");
    if (verifyModel) form.append("model", verifyModel);

    try {
      const created = await createVerifyJob(form);
      setVerifyJobState(created);

      const finished = await pollVerifyJob(created.job_id);
      if (finished.status === "failed") {
        throw new Error(finished.error ?? tVerify("job_failed"));
      }
      if (!finished.result) {
        throw new Error(tVerify("job_missing_result"));
      }

      setVerifyResult(finished.result);
    } catch (error: unknown) {
      setVerifyError(error instanceof Error ? error.message : tCommon("unknown_error"));
    } finally {
      setVerifyLoading(false);
    }
  }

  function clearVerifyFileA() {
    setVerifyFileA(null);
    setVerifyResult(null);
    setVerifyError(null);
  }

  function clearVerifyFileB() {
    setVerifyFileB(null);
    setVerifyResult(null);
    setVerifyError(null);
  }

  function clearUploadedFiles() {
    setEnrollQueue([]);
  }

  function selectExistingSpeaker(speaker: Speaker) {
    clearUploadedFiles();
    setEnrollName(speaker.name);
    setEnrollSelectedSpeakerId(speaker.id);
    setEnrollDropdownOpen(false);
    setEnrollSearchQuery("");
  }

  function selectNewSpeaker(name: string) {
    clearUploadedFiles();
    setEnrollName(name.trim());
    setEnrollSelectedSpeakerId(null);
    setEnrollDropdownOpen(false);
    setEnrollSearchQuery("");
  }

  function clearSpeaker() {
    clearUploadedFiles();
    setEnrollName("");
    setEnrollSelectedSpeakerId(null);
    setEnrollSearchQuery("");
    setTimeout(() => setEnrollDropdownOpen(true), 50);
  }

  function handleFilesSelected(files: File[]) {
    setEnrollQueue((previous) => {
      const existingKeys = new Set(previous.map((item) => item.key));
      const newItems: QueuedFile[] = files
        .filter((file) => !existingKeys.has(file.name + file.size))
        .map((file) => ({ key: file.name + file.size, file, status: "pending" }));
      return [...previous, ...newItems];
    });
  }

  function removeFile(key: string) {
    setEnrollQueue((previous) => previous.filter((item) => item.key !== key));
  }

  async function createEnrollJob(itemKey: string, formData: FormData): Promise<EnrollJobAccepted> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/enroll/jobs");
      xhr.responseType = "json";

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && event.total > 0) {
          const percent = Math.min(100, Math.max(0, (event.loaded / event.total) * 100));
          setEnrollQueue((previous) =>
            previous.map((item) =>
              item.key === itemKey
                ? { ...item, status: "uploading", uploadProgress: percent, message: undefined }
                : item
            )
          );
        }
      };

      xhr.upload.onloadend = () => {
        setEnrollQueue((previous) =>
          previous.map((item) =>
            item.key === itemKey && item.status !== "error"
              ? { ...item, status: "queueing", uploadProgress: 100, message: undefined }
              : item
          )
        );
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
          resolve(body as EnrollJobAccepted);
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

  async function startEnrollJob(jobId: string): Promise<EnrollJobState> {
    const response = await fetch(`/api/enroll/jobs/${jobId}/start`, {
      method: "POST",
    });
    const data =
      ((await response.json().catch(() => ({ detail: response.statusText }))) as EnrollJobState & {
        detail?: string;
      }) ?? null;

    if (!response.ok || !data) {
      throw new Error(data?.detail ?? tCommon("unknown_error"));
    }

    return data;
  }

  async function stagePendingUpload(
    item: QueuedFile,
    speakerId: number | null,
    speakerName: string
  ): Promise<StagedEnrollJob | null> {
    setEnrollQueue((previous) =>
      previous.map((queued) =>
        queued.key === item.key
          ? { ...queued, status: "uploading", uploadProgress: 0, message: undefined }
          : queued
      )
    );

    const form = new FormData();
    form.append("audio", item.file);
    form.append("speaker_name", speakerName);
    form.append("auto_start", "false");
    if (speakerId !== null) {
      form.append("speaker_id", String(speakerId));
    }

    try {
      const data = await createEnrollJob(item.key, form);
      if (!data.job_id) {
        throw new Error(tVerify("job_missing_result"));
      }

      setEnrollQueue((previous) =>
        previous.map((queued) =>
          queued.key === item.key
            ? {
                ...queued,
                status: "queueing",
                uploadProgress: 100,
                jobId: data.job_id,
                message: undefined,
              }
            : queued
        )
      );

      return { itemKey: item.key, jobId: data.job_id };
    } catch (error: unknown) {
      setEnrollQueue((previous) =>
        previous.map((queued) =>
          queued.key === item.key
            ? {
                ...queued,
                status: "error",
                message: error instanceof Error ? error.message : tCommon("unknown_error"),
              }
            : queued
        )
      );
      return null;
    }
  }

  async function createSpeaker(name: string): Promise<CreatedSpeaker> {
    const response = await fetch("/api/speakers", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data =
      ((await response.json().catch(() => ({ detail: response.statusText }))) as CreatedSpeaker & {
        detail?: string;
      }) ?? null;

    if (!response.ok || !data) {
      throw new Error(data?.detail ?? tCommon("unknown_error"));
    }

    return data;
  }

  async function startEnrollRun(overrideId?: number | null) {
    setEnrollIsRunning(true);

    let resolvedId: number | null =
      overrideId !== undefined ? overrideId : enrollSelectedSpeakerId;
    const stagedJobs: StagedEnrollJob[] = [];
    const pendingItems = enrollQueue.filter((item) => item.status === "pending");
    const speakerName = enrollName.trim();

    if (pendingItems.length > 0 && resolvedId === null) {
      try {
        const createdSpeaker = await createSpeaker(speakerName);
        resolvedId = createdSpeaker.id;
        setEnrollSelectedSpeakerId(createdSpeaker.id);
        setEnrollSpeakers((previous) => {
          const hasExisting = previous.some((speaker) => speaker.id === createdSpeaker.id);
          return hasExisting ? previous : [...previous, createdSpeaker];
        });
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : tCommon("unknown_error");
        setEnrollQueue((previous) =>
          previous.map((item) =>
            item.status === "pending" ? { ...item, status: "error", message } : item
          )
        );
        setEnrollIsRunning(false);
        return;
      }
    }

    if (pendingItems.length > 0) {
      const uploadResults = await Promise.all(
        pendingItems.map((item) => stagePendingUpload(item, resolvedId, speakerName))
      );

      for (const result of uploadResults) {
        if (result) {
          stagedJobs.push(result);
        }
      }
    }

    await Promise.all(
      stagedJobs.map(async (staged) => {
        setEnrollQueue((previous) =>
          previous.map((item) =>
            item.key === staged.itemKey
              ? { ...item, status: "queueing", message: undefined }
              : item
          )
        );

        try {
          const stored = await startEnrollJob(staged.jobId);
          if (stored.status === "failed") {
            throw new Error(stored.error ?? tVerify("job_failed"));
          }
          if (!stored.result) {
            throw new Error(tVerify("job_missing_result"));
          }

          setEnrollQueue((previous) =>
            previous.map((item) =>
              item.key === staged.itemKey
                ? { ...item, status: "done", uploadProgress: 100, message: undefined }
                : item
            )
          );
        } catch (error: unknown) {
          setEnrollQueue((previous) =>
            previous.map((item) =>
              item.key === staged.itemKey
                ? {
                    ...item,
                    status: "error",
                    message: error instanceof Error ? error.message : tCommon("unknown_error"),
                  }
                : item
            )
          );
        }
      })
    );

    if (stagedJobs.length > 0) {
      fetch("/api/speakers")
        .then((response) => response.json())
        .then((data: { speakers?: Speaker[] }) => setEnrollSpeakers(data.speakers ?? []))
        .catch(() => {});
    }

    setEnrollIsRunning(false);
  }

  async function handleEnroll() {
    const trimmedName = enrollName.trim();
    const pendingCount = enrollQueue.filter((item) => item.status === "pending").length;
    if (!trimmedName || pendingCount === 0 || enrollIsRunning) return;

    const exactMatch = enrollSpeakers.find(
      (speaker) => speaker.name.toLowerCase() === trimmedName.toLowerCase()
    );

    if (!enrollSelectedSpeakerId && exactMatch) {
      setEnrollDupDialogSpeaker(exactMatch);
      return;
    }

    await startEnrollRun();
  }

  async function confirmDuplicateExisting() {
    if (!enrollDupDialogSpeaker) return;
    const speaker = enrollDupDialogSpeaker;
    setEnrollDupDialogSpeaker(null);
    setEnrollSelectedSpeakerId(speaker.id);
    await startEnrollRun(speaker.id);
  }

  async function confirmDuplicateNew() {
    setEnrollDupDialogSpeaker(null);
    setEnrollSelectedSpeakerId(null);
    await startEnrollRun(null);
  }

  function closeDuplicateDialog() {
    setEnrollDupDialogSpeaker(null);
  }

  function resetDone() {
    clearUploadedFiles();
    setEnrollName("");
    setEnrollSelectedSpeakerId(null);
    setEnrollSearchQuery("");
  }

  const filteredSpeakers = enrollSearchQuery.trim()
    ? enrollSpeakers.filter((speaker) =>
        speaker.name.toLowerCase().includes(enrollSearchQuery.toLowerCase())
      )
    : enrollSpeakers;
  const pendingCount = enrollQueue.filter((item) => item.status === "pending").length;
  const canEnroll = !!enrollName.trim() && pendingCount > 0 && !enrollIsRunning;
  const allDone = enrollQueue.length > 0 && enrollQueue.every((item) => item.status === "done");
  const hasSpeaker = !!(enrollName && !enrollDropdownOpen);

  return (
    <BackgroundTasksContext.Provider
      value={{
        search: {
          file: searchFile,
          loading: searchLoading,
          results: searchResults,
          error: searchError,
          model: searchModel,
          limit: searchLimit,
          modelUsed: searchModelUsed,
          separateVocals: searchSeparateVocals,
          elapsedSeconds: searchElapsedSeconds,
          setFile: setSearchFile,
          setModel: setSearchModel,
          setLimit: setSearchLimit,
          setSeparateVocals: setSearchSeparateVocals,
          clear: clearSearch,
          start: startSearch,
        },
        verify: {
          fileA: verifyFileA,
          fileB: verifyFileB,
          loading: verifyLoading,
          result: verifyResult,
          error: verifyError,
          uploadProgress: verifyUploadProgress,
          jobState: verifyJobState,
          model: verifyModel,
          separateVocals: verifySeparateVocals,
          setFileA: setVerifyFileA,
          setFileB: setVerifyFileB,
          clearFileA: clearVerifyFileA,
          clearFileB: clearVerifyFileB,
          setModel: setVerifyModel,
          setSeparateVocals: setVerifySeparateVocals,
          start: startVerify,
        },
        enroll: {
          name: enrollName,
          queue: enrollQueue,
          isRunning: enrollIsRunning,
          speakers: enrollSpeakers,
          selectedSpeakerId: enrollSelectedSpeakerId,
          dupDialogSpeaker: enrollDupDialogSpeaker,
          dropdownOpen: enrollDropdownOpen,
          searchQuery: enrollSearchQuery,
          filteredSpeakers,
          pendingCount,
          canEnroll,
          allDone,
          hasSpeaker,
          setName: setEnrollName,
          setDropdownOpen: setEnrollDropdownOpen,
          setSearchQuery: setEnrollSearchQuery,
          clearUploadedFiles,
          selectExistingSpeaker,
          selectNewSpeaker,
          clearSpeaker,
          handleFilesSelected,
          removeFile,
          handleEnroll,
          confirmDuplicateExisting,
          confirmDuplicateNew,
          closeDuplicateDialog,
          resetDone,
        },
      }}
    >
      {children}
    </BackgroundTasksContext.Provider>
  );
}

export function useBackgroundTasks() {
  const context = useContext(BackgroundTasksContext);
  if (!context) {
    throw new Error("useBackgroundTasks must be used within BackgroundTasksProvider");
  }
  return context;
}