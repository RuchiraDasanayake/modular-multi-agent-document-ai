import type { ProductAutoScalarType } from "@/types/product-auto";

export interface ProductAutoBriefField {
  field_id: string;
  type: ProductAutoScalarType | "array[object]";
  group?: string;
  description: string;
  example_values: string[];
}

export interface ProductAutoBriefSample {
  file_id: string;
  source_sha256: string;
}

export interface ProductAutoBriefRevision {
  contract_version: 1;
  brief_id: string;
  owner_user_id: string;
  job_id: string;
  revision: number;
  audit_event_id: string;
  previous_event_id: string | null;
  actor_user_id: string;
  created_at: string;
  state: "draft" | "confirmed";
  intent: string;
  fields: ProductAutoBriefField[];
  sample_sources: ProductAutoBriefSample[];
  payload_sha256: string;
}

export interface ProductAutoBriefDetail {
  brief: ProductAutoBriefRevision | null;
  staleSampleFileIds: string[];
}

export interface ProductAutoBriefSuggestion {
  fields: ProductAutoBriefField[];
  clarification_questions: string[];
  provenance: {
    brief_revision: number;
    brief_payload_sha256: string;
    samples: { file_id: string; source_sha256: string; parser_id: string;
      excerpt_chars: number; truncated: boolean }[];
    model_id: string;
    prompt_sha256: string;
    input_chars: number;
    max_output_tokens: number;
    prompt_tokens: number | null;
    completion_tokens: number | null;
    latency_ms: number | null;
  };
}
