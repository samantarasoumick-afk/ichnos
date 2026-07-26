export type SensitivityScore = "LOW" | "MEDIUM" | "HIGH";

export type Classification = "UNCLASSIFIED" | "SENSITIVE" | "PII";

export type OperationalStatus = "HEALTHY" | "DEGRADED" | "AT_RISK" | "UNSTABLE";

export type Source = {
  id: string;
  name: string;
  type: string;
  connection_config: Record<string, unknown>;
  is_seed_data?: boolean;
};

export type DemoStatus = {
  demo_data_loaded: boolean;
  demo_source_count: number;
};

export type ContractStatus =
  | "NO_CONTRACT"
  | "PENDING_EVALUATION"
  | "COMPLIANT"
  | "BREACHED";

export type SystemRole = "SYSTEM_OF_RECORD" | "SYSTEM_OF_REFERENCE";

export type DataCategory = "MASTER" | "REFERENCE" | "TRANSACTIONAL" | "ANALYTICAL";

export type Dataset = {
  id: string;
  source_id: string;
  name: string;
  schema_name: string;
  owner: string;

  description?: string;
  ai_summary?: string;

  domain?: string;
  steward?: string;
  tags?: string;
  certification?: string;

  system_role?: SystemRole | null;
  data_category?: DataCategory | null;

  sensitivity_score?: SensitivityScore;
  total_columns?: number;
  pii_columns?: number;
  risk_score?: number;
  governance_status?: string;
  governance_score?: number;

  last_scanned_at?: string;
  freshness_status?: string;
  trust_score?: number;
  quality_score?: number;
  operational_status?: OperationalStatus;
  contract_status?: ContractStatus;

  view_count?: number;
  distinct_viewer_count?: number;
  last_viewed_at?: string | null;

  pending_certification_request_id?: string | null;
};

export type GovernanceOverview = {
  total_datasets: number;
  average_governance_score: number;
  missing_stewards: number;
  uncertified_datasets: number;
  critical_datasets: number;
  glossary_terms: number;
};

export type BusinessGlossaryTerm = {
  id: string;
  term: string;
  definition: string;
  domain?: string;
  owner?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
  is_seed_data?: boolean;
};

export type GlossaryTermLink = {
  id: string;
  term_id: string;
  term: string;
  definition: string;
  dataset_id: string;
  column_id?: string | null;
  column_name?: string | null;
  created_at?: string;
};

export type GlossaryTermLinkCreate = {
  term_id: string;
  dataset_id: string;
  column_id?: string;
};

export type BusinessProcess = {
  id: string;
  name: string;
  description?: string | null;
  narrative?: string | null;
  owner?: string | null;
  dataset_count: number;
  created_at?: string;
  updated_at?: string;
  is_seed_data?: boolean;
};

export type BusinessProcessCreate = {
  name: string;
  description?: string;
  narrative?: string;
  owner?: string;
};

export type BusinessProcessUpdate = {
  name?: string;
  description?: string;
  narrative?: string;
  owner?: string;
};

export type BusinessProcessDatasetSummary = {
  id: string;
  name: string;
  schema_name: string;
  data_category?: DataCategory | null;
  system_role?: SystemRole | null;
};

export type BusinessProcessLinkResult = {
  id: string;
  process_id: string;
  process_name: string;
  dataset_id: string;
  created_at?: string;
  glossary_term_created: boolean;
  glossary_term_name?: string | null;
};

export type DatasetColumn = {
  id: string;
  dataset_id: string;
  name: string;
  data_type: string;
  nullable: boolean;
  classification: Classification;
  sensitivity_score: SensitivityScore;
  confidence: number;
  detection_reason: string;
  recommendation: string;
  description?: string | null;
  sample_values?: string | null;
  masked: boolean;
};

export type Lineage = {
  id: string;
  upstream_dataset_id: string;
  downstream_dataset_id: string;
  transformation_type?: string | null;
  transformation_description?: string | null;
  filter_logic?: string | null;
  documentation_source: "AUTO" | "MANUAL";
};

export type ColumnLineage = {
  id: string;
  upstream_dataset_id: string;
  upstream_column_name: string;
  downstream_dataset_id: string;
  downstream_column_name: string;
  transformation_type?: string | null;
  transformation_description?: string | null;
  documentation_source: "AUTO" | "MANUAL";
};

export type LineageCreate = {
  upstream_dataset_id: string;
  downstream_dataset_id: string;
  transformation_type?: string;
  transformation_description?: string;
  filter_logic?: string;
};

export type LineageUpdate = {
  transformation_type?: string;
  transformation_description?: string;
  filter_logic?: string;
};

export type ConsentStatus =
  | "NOT_ASSESSED"
  | "CONSENT_OBTAINED"
  | "CONSENT_NOT_REQUIRED";

export type RetentionStatus = "NOT_SET" | "WITHIN_POLICY" | "OVERDUE";

export type GovernanceScorecard = {
  id: string;
  name: string;
  schema_name: string;
  owner?: string;
  steward?: string;
  domain?: string;
  tags?: string;
  certification?: string;
  system_role?: SystemRole | null;
  data_category?: DataCategory | null;
  governance_status: string;
  governance_score: number;
  risk_score: number;
  trust_score: number;
  sensitivity_score: SensitivityScore;
  quality_score: number;
  freshness_status: string;

  purpose?: string;
  consent_status?: ConsentStatus;
  retention_period_days?: number;
  retention_notes?: string;
  retention_status: RetentionStatus;
  privacy_score: number;

  contract_status?: ContractStatus;
  pending_certification_request_id?: string | null;
};

export type CertificationRequestStatus = "PENDING" | "APPROVED" | "REJECTED";

export type CertificationRequest = {
  id: string;
  dataset_id: string;
  requested_by: string;
  requested_by_email?: string;
  request_note?: string;
  status: CertificationRequestStatus;
  reviewed_by?: string;
  reviewed_by_email?: string;
  review_note?: string;
  created_at?: string;
  reviewed_at?: string;
};

export type DatasetGovernanceUpdate = {
  owner?: string;
  steward?: string;
  domain?: string;
  tags?: string;
  certification?: string;
  purpose?: string;
  consent_status?: ConsentStatus;
  retention_period_days?: number | null;
  retention_notes?: string;
  system_role?: SystemRole | null;
  data_category?: DataCategory | null;
};

export type BusinessGlossaryTermCreate = {
  term: string;
  definition: string;
  domain?: string;
  owner?: string;
  status?: string;
};

export type BusinessGlossaryTermUpdate = {
  term?: string;
  definition?: string;
  domain?: string;
  owner?: string;
  status?: string;
};

export type DataQuality = {
  id: string;
  dataset_id: string;
  completeness?: number;
  uniqueness?: number;
  validity?: number;
  consistency?: number;
  freshness?: number;
  overall_score?: number;
};

export type EffectiveQualityContributingEdge = {
  edge_id: string;
  upstream_dataset_id: string;
  upstream_effective_score: number;
  documentation_completeness: number;
  adjustment: number;
  contribution: number;
};

export type EffectiveQuality = {
  dataset_id: string;
  own_score?: number | null;
  effective_score?: number | null;
  contributing_edges: EffectiveQualityContributingEdge[];
};

export type PrivacyOverview = {
  total_datasets: number;
  average_privacy_score: number;
  datasets_needing_consent_review: number;
  datasets_overdue_retention: number;
  datasets_missing_purpose: number;
  sensitive_columns_by_dpdp_category: Record<string, number>;
  top_at_risk_datasets: {
    id: string;
    name: string;
    schema_name: string;
    privacy_score: number;
    consent_status: ConsentStatus | null;
    retention_status: RetentionStatus;
  }[];
};

export type AuditLogEntry = {
  id: string;
  actor_user_id?: string;
  actor_email?: string;
  action: string;
  resource_type?: string;
  resource_id?: string;
  details?: string;
  created_at: string;
};

export type UserRole = "admin" | "steward" | "data_owner" | "viewer";

export type TeamMember = {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at?: string;
};

export type TeamMemberInvite = {
  email: string;
  password: string;
  role: UserRole;
};

export type TeamMemberUpdate = {
  role?: UserRole;
  is_active?: boolean;
};

export type ContractColumnExpectation = {
  name: string;
  data_type?: string;
  nullable?: boolean;
  required: boolean;
};

export type DataContractStatus = "DRAFT" | "ACTIVE" | "DEPRECATED";

export type DataContract = {
  id: string;
  dataset_id: string;
  version: number;
  status: DataContractStatus;
  owner?: string;
  schema_expectations: { columns: ContractColumnExpectation[] };
  quality_thresholds?: Record<string, unknown> | null;
  freshness_sla_hours?: number | null;
  last_evaluated_at?: string | null;
  last_status?: "COMPLIANT" | "BREACHED" | null;
  last_breach_details?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type DataContractCreate = {
  dataset_id: string;
  owner?: string;
  schema_expectations: { columns: ContractColumnExpectation[] };
  quality_thresholds?: { min_overall_score: number } | null;
  freshness_sla_hours?: number | null;
};

export type UpstreamContractBreach = {
  dataset_id: string;
  dataset_name: string;
  schema_name: string;
  contract_id: string;
  contract_version: number;
  breach_details?: string | null;
};

export type AskSource = {
  type: "dataset" | "glossary_term";
  id: string;
  label: string;
};

export type AskResponse = {
  answer: string;
  sources: AskSource[];
};

export type ThreadType = "QUESTION" | "PROPOSAL" | "ISSUE";

export type ThreadStatus = "OPEN" | "RESOLVED";

export type GovernanceThreadReply = {
  id: string;
  thread_id: string;
  body: string;
  created_by: string;
  created_by_email?: string | null;
  created_at?: string;
};

export type GovernanceThread = {
  id: string;
  dataset_id?: string | null;
  dataset_label?: string | null;
  thread_type: ThreadType;
  title: string;
  body?: string | null;
  status: ThreadStatus;
  created_by: string;
  created_by_email?: string | null;
  created_at?: string;
  resolved_by?: string | null;
  resolved_by_email?: string | null;
  resolved_at?: string | null;
  resolution_note?: string | null;
  raised_for_user_id?: string | null;
  raised_for_email?: string | null;
  reply_count: number;
};

export type GovernanceThreadDetail = GovernanceThread & {
  replies: GovernanceThreadReply[];
};

export type GovernanceThreadCreate = {
  dataset_id?: string;
  thread_type: ThreadType;
  title: string;
  body?: string;
  raised_for_user_id?: string;
};

export type MaturityLevel = "NOT_STARTED" | "AD_HOC" | "REACTIVE" | "MANAGED" | "TRUSTED";

export type MaturityOverview = {
  total_datasets: number;
  level: MaturityLevel;
  overall_score: number;
  coverage: {
    pct_with_steward: number;
    pct_certified: number;
    pct_with_active_contract: number;
    pct_pii_with_documented_purpose: number;
    pct_high_sensitivity_with_assessed_risk: number;
  };
  average_scores: {
    governance_score: number;
    privacy_score: number;
    quality_score: number;
  };
  recommended_next_steps: string[];
};

export type RiskCategory =
  | "PRIVACY"
  | "SECURITY"
  | "OPERATIONAL"
  | "COMPLIANCE"
  | "DATA_QUALITY"
  | "OTHER";

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export type RiskStatus = "OPEN" | "MITIGATED" | "ACCEPTED" | "CLOSED";

export type ControlType = "PREVENTIVE" | "DETECTIVE" | "CORRECTIVE";

export type ControlStatus = "EFFECTIVE" | "INEFFECTIVE" | "NOT_TESTED";

export type Control = {
  id: string;
  name: string;
  description?: string | null;
  control_type: ControlType;
  status: ControlStatus;
  owner_user_id?: string | null;
  owner_email?: string | null;
  last_tested_at?: string | null;
  risk_count: number;
  created_at?: string;
  updated_at?: string;
};

export type ControlCreate = {
  name: string;
  description?: string;
  control_type: ControlType;
  owner_user_id?: string;
};

export type Risk = {
  id: string;
  title: string;
  description?: string | null;
  category: RiskCategory;
  likelihood: RiskLevel;
  impact: RiskLevel;
  status: RiskStatus;
  owner_user_id?: string | null;
  owner_email?: string | null;
  created_by: string;
  created_by_email?: string | null;
  inherent_score: number;
  inherent_level: RiskLevel;
  residual_score: number;
  residual_level: RiskLevel;
  effective_control_count: number;
  dataset_count: number;
  process_count: number;
  control_count: number;
  created_at?: string;
  updated_at?: string;
};

export type RiskCreate = {
  title: string;
  description?: string;
  category: RiskCategory;
  likelihood: RiskLevel;
  impact: RiskLevel;
  owner_user_id?: string;
};

export type RiskLinkedDataset = {
  id: string;
  name: string;
  schema_name: string;
};

export type RiskLinkedProcess = {
  id: string;
  name: string;
};

export type RiskLinkedControl = {
  id: string;
  name: string;
  status: ControlStatus;
};

export type RiskDetail = Risk & {
  linked_datasets: RiskLinkedDataset[];
  linked_processes: RiskLinkedProcess[];
  linked_controls: RiskLinkedControl[];
};
