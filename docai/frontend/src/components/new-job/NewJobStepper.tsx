import { StepStatusBadge } from "./NewJobBadges";

const STEPS = [
  { index: 0, label: "Job Setup" },
  { index: 1, label: "Extraction Profile" },
  { index: 2, label: "Document Queue" },
  { index: 3, label: "Runtime Configuration" },
  { index: 4, label: "Review Policy" },
  { index: 5, label: "Start Run" },
];

interface NewJobStepperProps {
  activeStep: number;
}

export default function NewJobStepper({ activeStep }: NewJobStepperProps) {
  return (
    <nav className="flex items-center gap-0 px-6 py-4 border-b border-white/5 bg-slate-950/40 shrink-0 overflow-x-auto scrollbar-hide">
      {STEPS.map((step, i) => {
        const status =
          i < activeStep ? "complete" : i === activeStep ? "active" : "pending";
        return (
          <div key={step.index} className="flex items-center">
            <div className="flex items-center gap-2 px-3 py-1.5">
              <StepStatusBadge status={status} />
              <span
                className={`text-xs font-medium whitespace-nowrap transition-colors ${
                  i === activeStep
                    ? "text-cyan-400"
                    : i < activeStep
                    ? "text-emerald-400"
                    : "text-slate-500"
                }`}
              >
                {step.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <span className="text-slate-700 text-xs mx-1 shrink-0">›</span>
            )}
          </div>
        );
      })}
    </nav>
  );
}
