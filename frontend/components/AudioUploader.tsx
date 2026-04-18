"use client";

import { useRef, useState, type DragEvent, type KeyboardEvent, type MouseEvent } from "react";
import { useTranslations } from "next-intl";
import { Upload, CheckCircle2, X } from "lucide-react";
import { cn } from "@/lib/utils";

type SingleProps = {
  id: string;
  label: string;
  accept?: string;
  multiple?: false;
  uploading?: boolean;
  onFile: (file: File) => void;
  onClear?: () => void;
};

type MultipleProps = {
  id: string;
  label: string;
  accept?: string;
  multiple: true;
  uploading?: boolean;
  onFiles: (files: File[]) => void;
  onClear?: () => void;
};

type Props = SingleProps | MultipleProps;

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AudioUploader(props: Props) {
  const { id, label, accept = "audio/*", uploading = false } = props;
  const t = useTranslations("uploader");
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileNames, setFileNames] = useState<string[]>([]);
  const [fileSizes, setFileSizes] = useState<number[]>([]);
  const [dragging, setDragging] = useState(false);

  function handleFiles(list: FileList | null) {
    if (!list || list.length === 0) return;
    if (props.multiple) {
      const files = Array.from(list);
      setFileNames(files.map((f) => f.name));
      setFileSizes(files.map((f) => f.size));
      props.onFiles(files);
    } else {
      const file = list[0];
      setFileNames([file.name]);
      setFileSizes([file.size]);
      props.onFile(file);
    }
  }

  function handleClear(e: MouseEvent) {
    e.stopPropagation();
    e.preventDefault();
    setFileNames([]);
    setFileSizes([]);
    if (inputRef.current) inputRef.current.value = "";
    props.onClear?.();
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (!uploading) handleFiles(e.dataTransfer.files);
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (!uploading) inputRef.current?.click();
    }
  }

  const hasFiles = fileNames.length > 0;
  const totalSize = fileSizes.reduce((a, b) => a + b, 0);

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={label}
      className={cn(
        "rounded-xl border-2 border-dashed p-8 text-center transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        uploading
          ? "border-primary/50 bg-primary/5 cursor-wait"
          : dragging
          ? "border-primary bg-primary/10 cursor-copy scale-[1.015]"
          : hasFiles
          ? "border-success bg-success/10 dark:bg-success/[0.08] cursor-pointer"
          : "border-border hover:border-primary/60 hover:bg-muted/40 cursor-pointer"
      )}
      onClick={() => { if (!uploading) inputRef.current?.click(); }}
      onKeyDown={onKeyDown}
      onDragOver={(e) => {
        e.preventDefault();
        if (!uploading) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept={accept}
        multiple={!!props.multiple}
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
      <div className="space-y-2">
        {/* State icon */}
        {uploading ? (
          <div className="w-full px-2 space-y-2">
            <div className="relative h-2 w-full overflow-hidden rounded-full bg-primary/15">
              <div
                className="absolute inset-y-0 w-[40%] rounded-full bg-primary"
                style={{ animation: "shimmer-bar 1.3s ease-in-out infinite" }}
              />
            </div>
          </div>
        ) : hasFiles ? (
          <CheckCircle2 className="mx-auto h-8 w-8 text-success animate-[fade-up_0.25s_ease-out_both]" />
        ) : (
          <Upload
            className={cn(
              "mx-auto h-8 w-8 transition-colors",
              dragging ? "text-primary scale-110" : "text-muted-foreground"
            )}
          />
        )}

        {/* Text content */}
        {uploading ? (
          <p className="text-sm font-medium text-primary">{t("uploading")}</p>
        ) : hasFiles ? (
          <div className="space-y-1">
            {props.multiple && fileNames.length > 1 ? (
              <p className="text-sm font-medium text-success">
                {t("files_selected", { count: fileNames.length })}
              </p>
            ) : (
              <p className="text-sm font-medium text-success truncate max-w-xs mx-auto" title={fileNames[0]}>
                {fileNames[0]}
              </p>
            )}
            {totalSize > 0 && (
              <p className="text-xs text-muted-foreground">
                {props.multiple && fileSizes.length > 1
                  ? `${formatSize(totalSize)} ${t("total")}`
                  : formatSize(fileSizes[0])}
              </p>
            )}
            <button
              type="button"
              onClick={handleClear}
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors mt-1 rounded focus-visible:outline-none focus-visible:underline"
            >
              <X className="size-3" />
              {t("clear")}
            </button>
          </div>
        ) : (
          <>
            <p className="text-sm font-medium">{label}</p>
            <p className="text-xs text-muted-foreground">
              {props.multiple ? t("drag_drop_multiple") : t("drag_drop")}
            </p>
          </>
        )}
      </div>
    </div>
  );
}

