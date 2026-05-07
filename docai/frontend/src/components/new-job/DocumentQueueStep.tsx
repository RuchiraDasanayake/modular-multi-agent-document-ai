import { useRef, ChangeEvent } from "react";
import { UploadCloud, FileText, X } from "lucide-react";
import { Card, CardContent, Button } from "@/components/ui";

interface DocumentQueueStepProps {
  files: File[];
  onFilesSelected: (files: File[]) => void;
  onRemoveFile: (index: number) => void;
  disabled?: boolean;
}

const ALLOWED_TYPES = ["application/pdf", "image/png", "image/jpeg"];

export default function DocumentQueueStep({
  files,
  onFilesSelected,
  onRemoveFile,
  disabled = false,
}: DocumentQueueStepProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files as FileList).filter((file) =>
        ALLOWED_TYPES.includes(file.type)
      );
      onFilesSelected([...files, ...newFiles]);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2 mb-1">
          <FileText className="h-4 w-4 opacity-70" />
          Document Queue
        </h2>
        <p className="text-xs text-slate-500">
          Stage documents for this job.
        </p>
      </div>

      {/* Upload area */}
      <div className="border-2 border-dashed border-white/10 rounded-lg p-8 flex flex-col items-center justify-center text-center bg-slate-900/30 hover:bg-slate-800/40 transition-colors group">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,image/png,image/jpeg"
          onChange={handleFileSelect}
          disabled={disabled}
          className="hidden"
        />
        <div className="bg-slate-900 p-3 rounded-full mb-3 group-hover:shadow-[0_0_15px_rgba(6,182,212,0.15)] transition-shadow">
          <UploadCloud className="h-6 w-6 text-cyan-400/60" />
        </div>
        <p className="text-sm font-medium text-slate-400 mb-1">
          {disabled ? "Upload disabled while submitting" : "Select files to stage"}
        </p>
        <p className="text-xs text-slate-600 font-mono mb-3">PDF, PNG, JPG</p>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled}
          className="border-white/10 hover:border-cyan-500/50"
          onClick={() => fileInputRef.current?.click()}
        >
          Select Files
        </Button>
      </div>

      {/* Staged files list */}
      {files.length > 0 ? (
        <Card className="overflow-hidden border-white/5">
          <div className="bg-slate-900/60 px-4 py-2 border-b border-white/5 text-[10px] uppercase font-bold text-slate-400 flex items-center justify-between">
            <span>Staged Documents</span>
            <span className="text-slate-500 font-mono font-normal normal-case">
              {files.length} file{files.length !== 1 ? "s" : ""}
            </span>
          </div>
          <CardContent className="p-0">
            <table className="w-full text-sm text-left border-collapse">
              <thead className="bg-slate-900/80 border-b border-white/5 text-slate-500 uppercase text-[9px] tracking-wider">
                <tr>
                  <th className="px-4 py-2">Filename</th>
                  <th className="px-4 py-2">Type</th>
                  <th className="px-4 py-2">Size</th>
                  <th className="px-4 py-2 w-10"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 bg-slate-800/10">
                {files.map((file, idx) => (
                  <tr key={idx} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-2 text-xs font-medium text-slate-200">
                        <FileText className="h-3.5 w-3.5 text-cyan-400/50 shrink-0" />
                        {file.name}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-xs text-slate-400">
                      {file.type === "application/pdf"
                        ? "PDF"
                        : file.type === "image/png"
                          ? "PNG"
                          : "JPG"}
                    </td>
                    <td className="px-4 py-2 text-xs text-slate-400">
                      {formatFileSize(file.size)}
                    </td>
                    <td className="px-4 py-2 text-center">
                      <button
                        onClick={() => onRemoveFile(idx)}
                        disabled={disabled}
                        className="inline-flex items-center justify-center p-1 rounded hover:bg-slate-700/50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        <X className="h-3.5 w-3.5 text-slate-500 hover:text-slate-300" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : (
        <div className="p-4 rounded-lg bg-slate-900/20 border border-slate-700/50 text-center">
          <p className="text-xs text-slate-500">
            No files staged yet. Select files above to begin.
          </p>
        </div>
      )}
    </div>
  );
}
