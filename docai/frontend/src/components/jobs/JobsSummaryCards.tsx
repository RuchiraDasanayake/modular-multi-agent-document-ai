"use client";

import { useEffect, useState } from "react";
import { listJobs } from "@/lib/docaiApi";
import type { JobOut } from "@/lib/docaiApi";

function SummaryCard({
  label,
  value,
  valueClass = "text-slate-200",
}: {
  label: string;
  value: number | string;
  valueClass?: string;
}) {
  return (
    <div className="glass-card rounded-lg px-4 py-3 border border-white/5">
      <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-2xl font-bold font-mono ${valueClass}`}>{value}</p>
    </div>
  );
}

export function JobsSummaryCards() {
  const [jobs, setJobs] = useState<JobOut[]>([]);

  useEffect(() => {
    const fetchJobs = async () => {
      try {
        // Fetch from the project
        const projectId = "proj-1"; // Default project
        const jobsList = await listJobs(projectId);
        setJobs(jobsList);
      } catch (err) {
        console.error("Failed to fetch jobs:", err);
      }
    };

    fetchJobs();
  }, []);

  const total = jobs.length;
  const training = jobs.filter((j) => j.job_type === "training").length;
  const production = jobs.filter((j) => j.job_type === "production").length;
  const completed = jobs.filter((j) => j.status === "completed").length;

  return (
    <div className="grid grid-cols-5 gap-3">
      <SummaryCard label="Total Jobs" value={total} />
      <SummaryCard
        label="Training Runs"
        value={training}
        valueClass="text-violet-400"
      />
      <SummaryCard
        label="Production Runs"
        value={production}
        valueClass="text-slate-300"
      />
      <SummaryCard
        label="In Progress"
        value={total - completed}
        valueClass={total - completed > 0 ? "text-amber-400" : "text-slate-500"}
      />
      <SummaryCard
        label="Completed"
        value={completed}
        valueClass="text-emerald-400"
      />
    </div>
  );
}
