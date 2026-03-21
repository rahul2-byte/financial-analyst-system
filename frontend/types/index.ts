// frontend/types/index.ts

export type Role = 'user' | 'assistant';

export type ChartType = 'line' | 'bar' | 'area';

/**
 * Generic data point for charts.
 */
export interface ChartDataPoint {
  [key: string]: string | number | undefined;
}

/**
 * Common financial data shapes for better strictness in chart components.
 */
export interface TimeSeriesDataPoint extends ChartDataPoint {
  timestamp: string | number;
}

/**
 * Specific shape for OHLC (Open, High, Low, Close) financial data.
 */
export interface OHLCDataPoint extends TimeSeriesDataPoint {
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

/**
 * Represents a chart payload for visualization.
 * Uses generics to allow better type inference of data keys.
 */
export interface ChartPayload<T extends ChartDataPoint = ChartDataPoint> {
  title: string;
  type: ChartType;
  data: T[]; 
  xAxisKey: Extract<keyof T, string>;
  seriesKeys: Extract<keyof T, string>[]; 
}

// SSE Event Types
export type StreamEvent = 
  | { type: 'text_delta'; content: string }
  | { type: 'chart'; content: ChartPayload }
  | { type: 'status'; message: string }
  | { type: 'error'; message?: string; content?: string }
  | { type: 'done' };

/**
 * Represents a single message in the chat history.
 */
export interface Message {
  id: string;
  role: Role;
  content: string; // Markdown text
  charts?: ChartPayload[]; // Attached charts
  timestamp: Date;
  isStreaming?: boolean;
}
