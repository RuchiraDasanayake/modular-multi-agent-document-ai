import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui";
import NewJobStepper from "@/components/new-job/NewJobStepper";
import JobSetupStep from "@/components/new-job/JobSetupStep";
import ExtractionSchemaStep from "@/components/new-job/ExtractionSchemaStep";
import DocumentQueueStep from "@/components/new-job/DocumentQueueStep";
import RuntimeConfigurationStep from "@/components/new-job/RuntimeConfigurationStep";
import ReviewPolicyStep from "@/components/new-job/ReviewPolicyStep";
import StartRunStep from "@/components/new-job/StartRunStep";
import {
  createJob,
  uploadDocument,
  createRun,
  attachDocumentToRun,
  executeRun,
  ExecuteRunResponse,
} from "@/lib/docaiApi";

const TOTAL_STEPS = 6;

export default function NewJobPage() {
  const { id } = useParams();
  const [step, setStep] = useState(0);

  // Step 1 - Job Setup
  const [jobName, setJobName] = useState("");
  const [runType, setRunType] = useState<"Training Run" | "Production Run">("Production Run");
  const [notes, setNotes] = useState("");

  // Step 2 - Extraction Profile
  const [selectedProfileId, setSelectedProfileId] = useState("");

  // Step 3 - Document Queue (staged files)
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);

  // Step 4 - Runtime Configuration
  const [ocrPreference, setOcrPreference] = useState("PaddleOCR (High Res)");
  const [parserPreference, setParserPreference] = useState("Layout-Aware Parser");
  const [localModel, setLocalModel] = useState("Qwen 3.5 9B");
  const [strategyMode, setStrategyMode] = useState("Deterministic Strategy Assignment");

  // Step 5 - Review Policy
  const [reviewOnLowConfidence, setReviewOnLowConfidence] = useState(true);
  const [reviewOnValidationFailure, setReviewOnValidationFailure] = useState(true);
  const [reviewOnRecoveryFailure, setReviewOnRecoveryFailure] = useState(false);

  // Submission state
  const [submitStatus, setSubmitStatus] = useState<
    "idle" | "submitting" | "success" | "error"
  >("idle");
  const [submitError, setSubmitError] = useState<string>("");
  const [createdJobId, setCreatedJobId] = useState<string>("");
  const [createdRunId, setCreatedRunId] = useState<string>("");
  const [executeResult, setExecuteResult] = useState<ExecuteRunResponse>();

  const handleAddFiles = (files: File[]) => {
    setStagedFiles(files);
  };

  const handleRemoveFile = (index: number) => {
    setStagedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async () => {
    if (!id) {
      setSubmitError("Project ID is missing");
      setSubmitStatus("error");
      return;
    }

    if (!jobName.trim()) {
      setSubmitError("Job name is required");
      setSubmitStatus("error");
      return;
    }

    if (!selectedProfileId) {
      setSubmitError("Select an extraction profile before continuing");
      setSubmitStatus("error");
      return;
    }

    if (stagedFiles.length === 0) {
      setSubmitError("At least one document is required");
      setSubmitStatus("error");
      return;
    }

    setSubmitStatus("submitting");
    setSubmitError("");

    try {
      // Step a: Create job
      const jobResp = await createJob(
        id,
        jobName,
        undefined,
        "practice",
        selectedProfileId,
      );
      const jobId = jobResp.job_id;
      setCreatedJobId(jobId);

      // Step e: Upload every staged file
      const uploadedDocs = [];
      for (const file of stagedFiles) {
        const docResp = await uploadDocument(jobId, file);
        uploadedDocs.push(docResp);
      }

      // Step f: Create run using backend default mode from selected profile
      const runResp = await createRun(jobId, undefined, "practice", "created");
      const runId = runResp.run_id;
      setCreatedRunId(runId);

      // Step g: Attach every uploaded document to run
      for (const doc of uploadedDocs) {
        await attachDocumentToRun(runId, doc.document_id);
      }

      // Step h: Execute run
      const execResp = await executeRun(runId, true);
      setExecuteResult(execResp);

      // Step i: Mark success only after executeRun() resolves
      setSubmitStatus("success");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Unknown error occurred";
      setSubmitError(message);
      setSubmitStatus("error");
    }
  };

  const isLastStep = step === TOTAL_STEPS - 1;

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden relative z-10">
      <header className="px-6 py-4 border-b border-white/10 glass-panel flex items-center gap-4 shrink-0">
        <Button
          variant="outline"
          size="sm"
          className="h-8 w-8 p-0 border-white/10 hover:border-cyan-500/50 hover:bg-cyan-500/5"
          asChild
        >
          <Link to={`/projects/${id}/jobs`}>
            <ChevronLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div>
          <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
            Create New Extraction Job
          </h1>
          <p className="text-xs text-slate-500 mt-0.5 font-mono">
            Configure a new batch of documents for processing.
          </p>
        </div>
      </header>

      <NewJobStepper activeStep={step} />

      <div className="flex-1 overflow-y-auto p-6 relative">
        <div className="max-w-3xl mx-auto">
          {step === 0 && (
            <JobSetupStep
              jobName={jobName}
              runType={runType}
              notes={notes}
              onJobName={setJobName}
              onRunType={setRunType}
              onNotes={setNotes}
            />
          )}
          {step === 1 && (
            <ExtractionSchemaStep
              projectId={id || ""}
              selectedProfileId={selectedProfileId}
              onSelect={setSelectedProfileId}
            />
          )}
          {step === 2 && (
            <DocumentQueueStep
              files={stagedFiles}
              onFilesSelected={handleAddFiles}
              onRemoveFile={handleRemoveFile}
              disabled={submitStatus === "submitting"}
            />
          )}
          {step === 3 && (
            <RuntimeConfigurationStep
              ocrPreference={ocrPreference}
              parserPreference={parserPreference}
              localModel={localModel}
              strategyMode={strategyMode}
              onOcr={setOcrPreference}
              onParser={setParserPreference}
              onModel={setLocalModel}
              onStrategyMode={setStrategyMode}
            />
          )}
          {step === 4 && (
            <ReviewPolicyStep
              runType={runType}
              reviewOnLowConfidence={reviewOnLowConfidence}
              reviewOnValidationFailure={reviewOnValidationFailure}
              reviewOnRecoveryFailure={reviewOnRecoveryFailure}
              onReviewOnLowConfidence={setReviewOnLowConfidence}
              onReviewOnValidationFailure={setReviewOnValidationFailure}
              onReviewOnRecoveryFailure={setReviewOnRecoveryFailure}
            />
          )}
          {step === 5 && (
            <StartRunStep
              jobName={jobName}
              stagedFileCount={stagedFiles.length}
              isSubmitting={submitStatus === "submitting"}
              submitStatus={submitStatus}
              submitError={submitError}
              createdJobId={createdJobId}
              createdRunId={createdRunId}
              executeResult={executeResult}
              onSubmit={handleSubmit}
              successJobLink={
                createdJobId ? `/projects/${id}/jobs/${createdJobId}` : undefined
              }
            />
          )}
        </div>
      </div>

      <footer className="px-6 py-4 border-t border-white/10 glass-panel flex items-center justify-between shrink-0">
        <div className="flex gap-2">
          {step > 0 ? (
            <Button variant="outline" className="border-white/10 text-slate-300" onClick={() => setStep((s) => s - 1)}>
              Back
            </Button>
          ) : (
            <Button variant="outline" className="border-white/10 text-slate-300" asChild>
              <Link to={`/projects/${id}/jobs`}>Cancel</Link>
            </Button>
          )}
        </div>
        {!isLastStep && (
          <Button
            variant="primary"
            onClick={() => setStep((s) => s + 1)}
          >
            Continue
          </Button>
        )}
      </footer>
    </div>
  );
}
