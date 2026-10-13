import type { ProductAutoField } from "@/types/product-auto";

export type ProductAutoRecipeState = "draft" | "approved_shadow" | "disabled";
export type ProductAutoRecipeAction = "draft_created" | "approved_shadow" | "disabled";

export interface ProductAutoRecipeSourceReview {
  job_id: string;
  run_id: string;
  doc_id: string;
  review_revision: number;
  review_audit_event_id: string;
  source_digest_sha256: string;
}

export interface ProductAutoRecipeRowGroup {
  group: string;
  field_ids: string[];
  alignment: "shared_ordinal";
}

export interface ProductAutoRecipeRevision {
  contract_version: 1;
  recipe_id: string;
  owner_user_id: string;
  revision: number;
  audit_event_id: string;
  previous_event_id: string | null;
  action: ProductAutoRecipeAction;
  state: ProductAutoRecipeState;
  actor_user_id: string;
  created_at: string;
  family_name: string;
  fields: ProductAutoField[];
  row_groups: ProductAutoRecipeRowGroup[];
  source_review: ProductAutoRecipeSourceReview;
  confirmed_row_groups: string[];
}

export interface ProductAutoRecipeDetail {
  recipe: ProductAutoRecipeRevision;
  auditTrail: ProductAutoRecipeRevision[];
}
