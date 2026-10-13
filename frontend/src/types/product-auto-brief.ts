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
  state: "draft";
  intent: string;
  fields: ProductAutoBriefField[];
  sample_sources: ProductAutoBriefSample[];
  payload_sha256: string;
}

export interface ProductAutoBriefDetail {
  brief: ProductAutoBriefRevision | null;
  staleSampleFileIds: string[];
}
