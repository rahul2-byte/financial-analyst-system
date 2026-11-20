// GENERATED — do not edit. Regenerate with `npm run gen:types`.
// Sources: protocol/schema/research_event.schema.json, protocol/schema/protocol.schema.json
// Schema title: "FIN-AI bridge protocol v1" (PROTOCOL_VERSION 1).
// Hand-written additions belong in src/protocol/{events,methods,version}.ts.

/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ResearchEvent".
 */
export type ResearchEvent =
  | RunStarted
  | RunCompleted
  | RunFailed
  | RunCancelled
  | StageStarted
  | StageCompleted
  | StageFailed
  | CheckStageResult
  | ToolStarted
  | ToolCompleted
  | ToolFailed
  | TextDelta
  | ModelRequestStarted
  | ModelResponseCompleted
  | ProviderAttemptStarted
  | ProviderRetrying
  | ProviderStreamStarted
  | ProviderCompleted
  | ProviderFailed
  | ToolProgress
  | ContextCompacted
  | SkillSelected
  | SourcesUpdated
  | ApprovalRequested
  | ApprovalResolved
  | ClarificationRequested
  | RouteDecisionMade;
export type ConversationId = string;
export type EventId = string;
export type OccurredAt = string;
export type RunId = string;
export type Sequence = number;
export type Query = string;
export type Type = 'run.started';
export type ArtifactPath = string | null;
export type CompletionReason = string | null;
export type DurationMs = number | null;
export type EvidenceAvailability = {
  [k: string]: unknown;
}[];
export type EvidenceStatus = string | null;
export type OutputReview = string | null;
export type RouteReasonCodes = string[];
export type TerminalStatus = string;
export type Type1 = 'run.completed';
export type Category = string;
export type Message = string;
export type Type2 = 'run.failed';
export type Reason = string;
export type Type3 = 'run.cancelled';
export type Label = string;
export type Stage = string;
export type Type4 = 'stage.started';
export type Detail = string | null;
export type Label1 = string;
export type Stage1 = string;
export type Type5 = 'stage.completed';
export type Label2 = string;
export type Message1 = string;
export type Stage2 = string;
export type Type6 = 'stage.failed';
export type Attempt = number;
export type Label3 = string;
export type MaxAttempts = number;
export type Passed = boolean;
export type Reasons = string[];
export type Retrying = boolean;
export type Stage3 = string;
export type Type7 = 'check.stage';
export type Detail1 = string | null;
export type Tool = string;
export type ToolId = string | null;
export type Type8 = 'tool.started';
export type Detail2 = string | null;
export type DurationMs1 = number | null;
export type Tool1 = string;
export type ToolId1 = string | null;
export type Type9 = 'tool.completed';
export type Message2 = string;
export type Tool2 = string;
export type ToolId2 = string | null;
export type Type10 = 'tool.failed';
export type Text = string;
export type Type11 = 'response.delta';
export type Model = string;
export type Round = number;
export type Type12 = 'model.request.started';
export type HasToolCalls = boolean;
export type Round1 = number;
export type Type13 = 'model.response.completed';
export type Attempt1 = number;
export type Provider = string;
export type Type14 = 'provider.attempt.started';
export type Attempt2 = number;
export type DelayMs = number;
export type Provider1 = string;
export type Reason1 = string;
export type StatusCode = number | null;
export type Type15 = 'provider.retrying';
export type Attempt3 = number;
export type FirstByteMs = number;
export type Provider2 = string;
export type Type16 = 'provider.stream.started';
export type Attempts = number;
export type DurationMs2 = number;
export type FirstTokenMs = number | null;
export type ModelId = string | null;
export type Provider3 = string;
export type Type17 = 'provider.completed';
export type CompletionTokens = number | null;
export type PromptTokens = number | null;
export type TotalTokens = number | null;
export type Verified = boolean;
export type Attempts1 = number;
export type DurationMs3 = number | null;
export type Message3 = string;
export type ModelId1 = string | null;
export type PartialOutput = boolean | null;
export type Phase = string;
export type Provider4 = string;
export type Reason2 = string | null;
export type StatusCode1 = number | null;
export type Timeout = boolean | null;
export type Type18 = 'provider.failed';
export type Message4 = string;
export type Tool3 = string;
export type ToolId3 = string;
export type Type19 = 'tool.progress';
export type CompactedMessages = number;
export type EstimatedTokens = number;
export type Type20 = 'context.compacted';
export type PackageHash = string;
export type SkillId = string;
export type Type21 = 'skill.selected';
export type Version = string;
export type Sources = {
  [k: string]: string;
}[];
export type Type22 = 'sources.updated';
export type Details = string | null;
export type Prompt = string;
export type Type23 = 'approval.requested';
export type Decision = 'approved' | 'rejected' | 'revised';
export type Type24 = 'approval.resolved';
export type Prompt1 = string;
export type Type25 = 'clarification.requested';
export type Confidence = number;
export type EscalationReason = string | null;
export type EvidenceSufficient = boolean | null;
export type ExecutionMode = string;
export type Intent = string;
export type ModelTier = string;
export type NextAction = string | null;
export type PromptInjectionRisk = string;
export type Reason3 = string;
export type ReasonCodes = string[];
export type RequiredTools = string[];
export type RiskFlags = string[];
export type SelectedModel = string | null;
export type SelectedProvider = string | null;
export type Type26 = 'route.decision.made';
export type Level = 'debug' | 'info' | 'warning' | 'error';
export type Message5 = string;
export type Name = string;
export type Version1 = string;
export type Candidates = DisplayCandidate[] | null;
export type Exchange = string;
export type Name1 = string;
export type Symbol = string;
export type Detail3 = string | null;
export type FailedNouns = string[] | null;
export type FailureDetail = string | null;
export type Friendly = string | null;
export type Instrument = string | null;
export type Label4 = string | null;
export type Lines = string[] | null;
export type Notice = string | null;
export type Noun = string | null;
export type ReviewNote = string | null;
export type ReviewUnavailable = boolean | null;
export type Sources1 = DisplaySource[] | null;
export type Host = string | null;
export type Label5 = string;
export type Url = string;
export type Code = number;
export type Data = {
  [k: string]: unknown;
} | null;
export type Message6 = string;
export type ProtocolVersion = number;
export type Columns = number;
export type Rows = number;
export type DataDir = string;
export type Mode = 'guided' | 'review' | 'autonomous';
export type FallbackId = string | null;
export type Id = string;
export type ProtocolVersion1 = number;
export type ServerVersion = string;
export type Id1 = string;
export type MessageCount = number;
export type RunCount = number;
export type Title = string;
export type Jsonrpc = '2.0';
export type Method = string;
export type Params = {
  [k: string]: unknown;
} | null;
export type Importance = 'major' | 'supporting' | 'minor';
export type SourceRefs = number[];
export type Text1 = string;
export type ObservedThroughText = string | null;
export type Name2 = string;
export type Reason4 = string | null;
export type Status = 'available' | 'degraded' | 'unavailable';
export type Sources2 = ReportSourceStatus[];
export type Status1 = 'complete' | 'limited';
export type Exchange1 = string | null;
export type Name3 = string | null;
export type Symbol1 = string;
export type AsOfText = string | null;
export type Label6 = string;
export type SourceRef = number | null;
export type ValueText = string;
export type AsOfText1 = string | null;
export type ChangeText = string | null;
export type Direction = ('up' | 'down' | 'flat') | null;
export type PriceText = string;
export type SourceRefs1 = number[];
export type Text2 = string;
export type Direction1 = 'bullish' | 'bearish' | 'neutral' | 'unavailable';
export type Name4 = string;
export type PercentileText = string | null;
export type StateText = string | null;
export type Strength = number | null;
export type ValueText1 = string;
export type FreshnessText = string | null;
export type Host1 = string | null;
export type Label7 = string;
export type Ref = number;
export type RetrievedText = string | null;
export type Trust = string | null;
export type Url1 = string;
export type HighText = string;
export type LowText = string;
export type PeriodText = string;
/**
 * @minItems 2
 * @maxItems 48
 */
export type Points = [number, number, ...number[]];
export type DetailedAnalysis = string | null;
export type Disclaimer = string;
export type Drivers = ReportDriver[];
export type FinalView = string | null;
export type KeyFigures = ReportKeyFigure[];
export type Kind = 'report' | 'lookup';
export type Limitations = string[];
export type Risks = ReportRisk[];
export type Signals = ReportSignal[];
export type Sources3 = ReportSource[];
export type StanceText = string | null;
export type Summary = string;
export type Id2 = number;
export type Jsonrpc1 = '2.0';
export type Method1 = string;
export type Params1 = {
  [k: string]: unknown;
} | null;
export type Id3 = number;
export type Jsonrpc2 = '2.0';
export type Result = {
  [k: string]: unknown;
} | null;
export type ClientRunId = string;
export type Cancelled = boolean;
export type ClientRunId1 = string;
export type Event =
  | RunStarted
  | RunCompleted
  | RunFailed
  | RunCancelled
  | StageStarted
  | StageCompleted
  | StageFailed
  | CheckStageResult
  | ToolStarted
  | ToolCompleted
  | ToolFailed
  | TextDelta
  | ModelRequestStarted
  | ModelResponseCompleted
  | ProviderAttemptStarted
  | ProviderRetrying
  | ProviderStreamStarted
  | ProviderCompleted
  | ProviderFailed
  | ToolProgress
  | ContextCompacted
  | SkillSelected
  | SourcesUpdated
  | ApprovalRequested
  | ApprovalResolved
  | ClarificationRequested
  | RouteDecisionMade;
export type ArtifactPath1 = string | null;
export type ClientRunId2 = string;
export type EvidenceAvailability1 = ReportSourceStatus[] | null;
export type EvidenceStatus1 = string | null;
export type Message7 = string | null;
export type Outcome = 'completed' | 'failed' | 'cancelled' | 'clarification' | 'error';
export type RunId1 = string | null;
export type ClientRunId3 = string;
export type Mode1 = 'guided' | 'review' | 'autonomous';
export type Query1 = string;
export type Accepted = true;
export type Queries = string[];
export type Limit = number;
export type Id4 = string;
export type LastActivity = string;
export type LastStatus = string;
export type MessageCount1 = number;
export type RunCount1 = number;
export type Title1 = string;
export type Sessions = SessionSummary[];
export type IdPrefix = string;
export type Limit1 = number;
export type LedgerPath = string;
export type Records = {
  [k: string]: unknown;
}[];

export interface FINAIProtocol {
  event?: ResearchEvent;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "RunStarted".
 */
export interface RunStarted {
  meta: EventMeta;
  query: Query;
  type: Type;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "EventMeta".
 */
export interface EventMeta {
  conversation_id: ConversationId;
  event_id: EventId;
  occurred_at: OccurredAt;
  run_id: RunId;
  sequence: Sequence;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "RunCompleted".
 */
export interface RunCompleted {
  artifact_path?: ArtifactPath;
  completion_reason?: CompletionReason;
  duration_ms?: DurationMs;
  evidence_availability?: EvidenceAvailability;
  evidence_status?: EvidenceStatus;
  meta: EventMeta;
  output_review?: OutputReview;
  route_reason_codes?: RouteReasonCodes;
  terminal_status: TerminalStatus;
  type: Type1;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "RunFailed".
 */
export interface RunFailed {
  category?: Category;
  message: Message;
  meta: EventMeta;
  type: Type2;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "RunCancelled".
 */
export interface RunCancelled {
  meta: EventMeta;
  reason?: Reason;
  type: Type3;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "StageStarted".
 */
export interface StageStarted {
  label: Label;
  meta: EventMeta;
  stage: Stage;
  type: Type4;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "StageCompleted".
 */
export interface StageCompleted {
  detail?: Detail;
  label: Label1;
  meta: EventMeta;
  stage: Stage1;
  type: Type5;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "StageFailed".
 */
export interface StageFailed {
  label: Label2;
  message: Message1;
  meta: EventMeta;
  stage: Stage2;
  type: Type6;
  [k: string]: unknown;
}
/**
 * Outcome of one answer-verification stage for one draft.
 *
 * ``attempt`` is the repair retry this result triggers when ``retrying`` is
 * true, otherwise the number of repair retries already used; ``max_attempts``
 * is the shared repair budget.
 *
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "CheckStageResult".
 */
export interface CheckStageResult {
  attempt: Attempt;
  label: Label3;
  max_attempts: MaxAttempts;
  meta: EventMeta;
  passed: Passed;
  reasons?: Reasons;
  retrying?: Retrying;
  stage: Stage3;
  type: Type7;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ToolStarted".
 */
export interface ToolStarted {
  detail?: Detail1;
  meta: EventMeta;
  tool: Tool;
  tool_id?: ToolId;
  type: Type8;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ToolCompleted".
 */
export interface ToolCompleted {
  detail?: Detail2;
  duration_ms?: DurationMs1;
  meta: EventMeta;
  tool: Tool1;
  tool_id?: ToolId1;
  type: Type9;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ToolFailed".
 */
export interface ToolFailed {
  message: Message2;
  meta: EventMeta;
  tool: Tool2;
  tool_id?: ToolId2;
  type: Type10;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "TextDelta".
 */
export interface TextDelta {
  meta: EventMeta;
  text: Text;
  type: Type11;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ModelRequestStarted".
 */
export interface ModelRequestStarted {
  meta: EventMeta;
  model: Model;
  round: Round;
  type: Type12;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ModelResponseCompleted".
 */
export interface ModelResponseCompleted {
  has_tool_calls?: HasToolCalls;
  meta: EventMeta;
  round: Round1;
  type: Type13;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ProviderAttemptStarted".
 */
export interface ProviderAttemptStarted {
  attempt: Attempt1;
  meta: EventMeta;
  provider?: Provider;
  type: Type14;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ProviderRetrying".
 */
export interface ProviderRetrying {
  attempt: Attempt2;
  delay_ms: DelayMs;
  meta: EventMeta;
  provider?: Provider1;
  reason: Reason1;
  status_code?: StatusCode;
  type: Type15;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ProviderStreamStarted".
 */
export interface ProviderStreamStarted {
  attempt: Attempt3;
  first_byte_ms: FirstByteMs;
  meta: EventMeta;
  provider?: Provider2;
  type: Type16;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ProviderCompleted".
 */
export interface ProviderCompleted {
  attempts: Attempts;
  duration_ms: DurationMs2;
  first_token_ms?: FirstTokenMs;
  meta: EventMeta;
  model_id?: ModelId;
  provider?: Provider3;
  type: Type17;
  usage?: TokenUsage | null;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "TokenUsage".
 */
export interface TokenUsage {
  completion_tokens?: CompletionTokens;
  prompt_tokens?: PromptTokens;
  total_tokens?: TotalTokens;
  verified?: Verified;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ProviderFailed".
 */
export interface ProviderFailed {
  attempts: Attempts1;
  duration_ms?: DurationMs3;
  message: Message3;
  meta: EventMeta;
  model_id?: ModelId1;
  partial_output?: PartialOutput;
  phase: Phase;
  provider?: Provider4;
  reason?: Reason2;
  status_code?: StatusCode1;
  timeout?: Timeout;
  type: Type18;
  usage?: TokenUsage | null;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ToolProgress".
 */
export interface ToolProgress {
  message: Message4;
  meta: EventMeta;
  tool: Tool3;
  tool_id: ToolId3;
  type: Type19;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ContextCompacted".
 */
export interface ContextCompacted {
  compacted_messages: CompactedMessages;
  estimated_tokens: EstimatedTokens;
  meta: EventMeta;
  type: Type20;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "SkillSelected".
 */
export interface SkillSelected {
  meta: EventMeta;
  package_hash: PackageHash;
  skill_id: SkillId;
  type: Type21;
  version: Version;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "SourcesUpdated".
 */
export interface SourcesUpdated {
  meta: EventMeta;
  sources: Sources;
  type: Type22;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ApprovalRequested".
 */
export interface ApprovalRequested {
  details?: Details;
  meta: EventMeta;
  prompt: Prompt;
  type: Type23;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ApprovalResolved".
 */
export interface ApprovalResolved {
  decision: Decision;
  meta: EventMeta;
  type: Type24;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ClarificationRequested".
 */
export interface ClarificationRequested {
  meta: EventMeta;
  prompt: Prompt1;
  type: Type25;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "RouteDecisionMade".
 */
export interface RouteDecisionMade {
  confidence: Confidence;
  escalation_reason?: EscalationReason;
  evidence_sufficient?: EvidenceSufficient;
  execution_mode: ExecutionMode;
  intent: Intent;
  meta: EventMeta;
  model_tier: ModelTier;
  next_action?: NextAction;
  prompt_injection_risk?: PromptInjectionRisk;
  reason?: Reason3;
  reason_codes?: ReasonCodes;
  required_tools?: RequiredTools;
  risk_flags?: RiskFlags;
  selected_model?: SelectedModel;
  selected_provider?: SelectedProvider;
  type: Type26;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "BridgeLogParams".
 */
export interface BridgeLogParams {
  level: Level;
  message: Message5;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ClientInfo".
 */
export interface ClientInfo {
  name: Name;
  version: Version1;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ContextCompactParams".
 */
export interface ContextCompactParams {}
/**
 * Free-form result of ``FinAIRepl.compact_context()``.
 *
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ContextCompactResult".
 */
export interface ContextCompactResult {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ContextInfoParams".
 */
export interface ContextInfoParams {}
/**
 * Free-form output of the ``ContextBudget`` used by ``/context``.
 *
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ContextInfoResult".
 */
export interface ContextInfoResult {
  [k: string]: unknown;
}
/**
 * Sanitized, presentation-ready strings computed by the Python runtime.
 *
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "Display".
 */
export interface Display {
  candidates?: Candidates;
  detail?: Detail3;
  failed_nouns?: FailedNouns;
  failure_detail?: FailureDetail;
  friendly?: Friendly;
  instrument?: Instrument;
  label?: Label4;
  lines?: Lines;
  notice?: Notice;
  noun?: Noun;
  review_note?: ReviewNote;
  review_unavailable?: ReviewUnavailable;
  sources?: Sources1;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "DisplayCandidate".
 */
export interface DisplayCandidate {
  exchange: Exchange;
  name: Name1;
  symbol: Symbol;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "DisplaySource".
 */
export interface DisplaySource {
  host?: Host;
  label: Label5;
  url: Url;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ErrorObject".
 */
export interface ErrorObject {
  code: Code;
  data?: Data;
  message: Message6;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "InitializeParams".
 */
export interface InitializeParams {
  client: ClientInfo;
  protocol_version: ProtocolVersion;
  terminal: TerminalInfo;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "TerminalInfo".
 */
export interface TerminalInfo {
  columns: Columns;
  rows: Rows;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "InitializeResult".
 */
export interface InitializeResult {
  data_dir: DataDir;
  mode: Mode;
  model?: ModelInfo | null;
  protocol_version: ProtocolVersion1;
  server_version: ServerVersion;
  session: SessionInfo;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ModelInfo".
 */
export interface ModelInfo {
  fallback_id?: FallbackId;
  id: Id;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "SessionInfo".
 */
export interface SessionInfo {
  id: Id1;
  message_count: MessageCount;
  run_count: RunCount;
  title: Title;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "Notification".
 */
export interface Notification {
  jsonrpc: Jsonrpc;
  method: Method;
  params?: Params;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ReportDriver".
 */
export interface ReportDriver {
  importance: Importance;
  source_refs?: SourceRefs;
  text: Text1;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ReportEvidence".
 */
export interface ReportEvidence {
  observed_through_text?: ObservedThroughText;
  sources?: Sources2;
  status: Status1;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ReportSourceStatus".
 */
export interface ReportSourceStatus {
  name: Name2;
  reason?: Reason4;
  status: Status;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ReportInstrument".
 */
export interface ReportInstrument {
  exchange?: Exchange1;
  name?: Name3;
  symbol: Symbol1;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ReportKeyFigure".
 */
export interface ReportKeyFigure {
  as_of_text?: AsOfText;
  label: Label6;
  source_ref?: SourceRef;
  value_text: ValueText;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ReportQuote".
 */
export interface ReportQuote {
  as_of_text?: AsOfText1;
  change_text?: ChangeText;
  direction?: Direction;
  price_text: PriceText;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ReportRisk".
 */
export interface ReportRisk {
  source_refs?: SourceRefs1;
  text: Text2;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ReportSignal".
 */
export interface ReportSignal {
  direction: Direction1;
  name: Name4;
  percentile_text?: PercentileText;
  state_text?: StateText;
  strength?: Strength;
  value_text: ValueText1;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ReportSource".
 */
export interface ReportSource {
  freshness_text?: FreshnessText;
  host?: Host1;
  label: Label7;
  ref: Ref;
  retrieved_text?: RetrievedText;
  trust?: Trust;
  url: Url1;
  [k: string]: unknown;
}
/**
 * Closing prices resampled to at most 48 points and scaled to 0..1 in Python.
 *
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ReportSparkline".
 */
export interface ReportSparkline {
  high_text: HighText;
  low_text: LowText;
  period_text: PeriodText;
  points: Points;
  [k: string]: unknown;
}
/**
 * Display-ready report. Every ``*_text`` field is final text from Python.
 *
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ReportView".
 */
export interface ReportView {
  detailed_analysis?: DetailedAnalysis;
  disclaimer: Disclaimer;
  drivers?: Drivers;
  evidence: ReportEvidence;
  final_view?: FinalView;
  instrument?: ReportInstrument | null;
  key_figures?: KeyFigures;
  kind: Kind;
  limitations?: Limitations;
  quote?: ReportQuote | null;
  risks?: Risks;
  signals?: Signals;
  sources?: Sources3;
  sparkline?: ReportSparkline | null;
  stance_text?: StanceText;
  summary: Summary;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "Request".
 */
export interface Request {
  id: Id2;
  jsonrpc: Jsonrpc1;
  method: Method1;
  params?: Params1;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "Response".
 */
export interface Response {
  error?: ErrorObject | null;
  id: Id3;
  jsonrpc: Jsonrpc2;
  result?: Result;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "RunCancelParams".
 */
export interface RunCancelParams {
  client_run_id: ClientRunId;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "RunCancelResult".
 */
export interface RunCancelResult {
  cancelled: Cancelled;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "RunEventParams".
 */
export interface RunEventParams {
  client_run_id: ClientRunId1;
  display: Display | null;
  event: Event;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "RunFinishedParams".
 */
export interface RunFinishedParams {
  artifact_path: ArtifactPath1;
  client_run_id: ClientRunId2;
  evidence_availability?: EvidenceAvailability1;
  evidence_status?: EvidenceStatus1;
  message: Message7;
  outcome: Outcome;
  report?: ReportView | null;
  run_id: RunId1;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "RunStartParams".
 */
export interface RunStartParams {
  client_run_id: ClientRunId3;
  mode: Mode1;
  query: Query1;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "RunStartResult".
 */
export interface RunStartResult {
  accepted: Accepted;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "SessionHistoryParams".
 */
export interface SessionHistoryParams {}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "SessionHistoryResult".
 */
export interface SessionHistoryResult {
  queries: Queries;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "SessionListParams".
 */
export interface SessionListParams {
  limit?: Limit;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "SessionListResult".
 */
export interface SessionListResult {
  sessions: Sessions;
  [k: string]: unknown;
}
/**
 * Shape returned by ``SessionStore.list_sessions``.
 *
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "SessionSummary".
 */
export interface SessionSummary {
  id: Id4;
  last_activity: LastActivity;
  last_status: LastStatus;
  message_count: MessageCount1;
  run_count: RunCount1;
  title: Title1;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "SessionNewParams".
 */
export interface SessionNewParams {}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "SessionNewResult".
 */
export interface SessionNewResult {
  session: SessionInfo;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "SessionResumeParams".
 */
export interface SessionResumeParams {
  id_prefix: IdPrefix;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "SessionResumeResult".
 */
export interface SessionResumeResult {
  session: SessionInfo;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ShutdownParams".
 */
export interface ShutdownParams {}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "ShutdownResult".
 */
export interface ShutdownResult {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "TraceTailParams".
 */
export interface TraceTailParams {
  limit?: Limit1;
}
/**
 * This interface was referenced by `FINAIProtocol`'s JSON-Schema
 * via the `definition` "TraceTailResult".
 */
export interface TraceTailResult {
  ledger_path: LedgerPath;
  records: Records;
  [k: string]: unknown;
}
