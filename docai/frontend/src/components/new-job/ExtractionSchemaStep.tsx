import { useEffect, useState } from "react";
import { FileDigit, Loader2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { listExtractionProfiles, ExtractionProfileOut } from "@/lib/docaiApi";

interface ExtractionSchemaStepProps {
  projectId: string;
  selectedProfileId: string;
  onSelect: (id: string) => void;
}

export default function ExtractionSchemaStep({
  projectId,
  selectedProfileId,
  onSelect,
}: ExtractionSchemaStepProps) {
  const [profiles, setProfiles] = useState<ExtractionProfileOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) {
      setProfiles([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    listExtractionProfiles(projectId)
      .then((data) => {
        setProfiles(data);
        const preferred = data.find((item) => item.is_default) ?? data[0];
        if (preferred && !selectedProfileId) {
          onSelect(preferred.profile_id);
          return;
        }
        if (
          selectedProfileId &&
          data.length > 0 &&
          !data.some((item) => item.profile_id === selectedProfileId)
        ) {
          onSelect(preferred.profile_id);
        }
      })
      .catch(() => setError("Failed to load extraction profiles"))
      .finally(() => setLoading(false));
  }, [projectId, selectedProfileId, onSelect]);

  const selected = profiles.find((profile) => profile.profile_id === selectedProfileId) ?? null;

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2 mb-1">
          <FileDigit className="h-4 w-4 opacity-70" />
          Extraction Profile
        </h2>
        <p className="text-xs text-slate-500">
          Select the extraction profile that controls schema, default mode, OCR strategy, and validation level.
        </p>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Loader2 className="h-3 w-3 animate-spin" />
          Loading extraction profiles...
        </div>
      )}

      {!loading && error && <p className="text-xs text-red-400">{error}</p>}

      {!loading && !error && profiles.length === 0 && (
        <p className="text-xs text-slate-500">
          No extraction profiles found for this project. Create an Extraction Profile before creating a job.
        </p>
      )}

      {!loading && profiles.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {profiles.map((profile) => {
            const active = selectedProfileId === profile.profile_id;
            return (
              <button
                key={profile.profile_id}
                type="button"
                onClick={() => onSelect(profile.profile_id)}
                className={`p-4 rounded-lg border text-left transition-all relative ${
                  active
                    ? "border-cyan-500 bg-cyan-500/10 shadow-[0_0_15px_rgba(6,182,212,0.15)]"
                    : "border-white/10 bg-slate-900/50 hover:bg-slate-800/80"
                }`}
              >
                {active && (
                  <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_5px_rgba(6,182,212,0.8)]" />
                )}
                <p className={`text-sm font-semibold mb-1 ${active ? "text-cyan-400" : "text-slate-200"}`}>
                  {profile.name}
                </p>
                <p className="text-[10px] font-mono text-slate-500">schema_id: {profile.schema_id}</p>
                <p className="text-[10px] font-mono text-slate-500">mode: {profile.mode}</p>
                <p className="text-[10px] font-mono text-slate-500">ocr: {profile.ocr_strategy}</p>
                <p className="text-[10px] font-mono text-slate-500">validation: {profile.validation_level}</p>
                {profile.is_default && (
                  <p className="mt-1 text-[10px] font-bold uppercase tracking-wider text-cyan-400">
                    Default Profile
                  </p>
                )}
              </button>
            );
          })}
        </div>
      )}

      {selected && (
        <Card className="glass-card border-white/5">
          <CardContent className="p-5 space-y-4">
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
              Profile Summary - {selected.name}
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Profile ID</p>
                <p className="text-xs font-mono text-slate-100 break-all">{selected.profile_id}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Schema</p>
                <p className="text-sm font-bold text-slate-100">{selected.schema_id}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Mode</p>
                <p className="text-sm font-bold text-slate-100">{selected.mode}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">OCR Strategy</p>
                <p className="text-sm text-slate-100">{selected.ocr_strategy}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Validation</p>
                <p className="text-sm text-slate-100">{selected.validation_level}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
