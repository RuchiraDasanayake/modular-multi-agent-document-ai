import { Save, CheckCircle, AlertTriangle } from "lucide-react";
import { Card, CardContent, Button } from "@/components/ui";

export default function ReviewActionsPanel() {
  return (
    <Card className="glass-card border-white/5">
      <CardContent className="p-4">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">
          Review Actions
        </h3>
        <p className="text-[10px] text-amber-400/70 font-mono mb-4">
          Mock only — no actions are persisted to backend.
        </p>
        <div className="flex flex-col gap-2">
          <Button
            variant="outline"
            disabled
            className="justify-start text-slate-500 border-white/10 cursor-not-allowed"
          >
            <Save className="mr-2 h-4 w-4" />
            Save Correction (Mock)
          </Button>
          <Button
            variant="outline"
            disabled
            className="justify-start text-slate-500 border-white/10 cursor-not-allowed"
          >
            <CheckCircle className="mr-2 h-4 w-4" />
            Approve Final Output (Mock)
          </Button>
          <Button
            variant="outline"
            disabled
            className="justify-start text-slate-500 border-white/10 cursor-not-allowed"
          >
            <AlertTriangle className="mr-2 h-4 w-4" />
            Mark Needs Review (Mock)
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
