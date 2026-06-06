export interface SchedulerStatus {
  running: boolean;
  paused: boolean;
  mode: string;
  batch_size: number;
  keywords_scanned: number;
  new_seeds_found: number;
  current_keyword: string | null;
  started_at: string | null;
  interval_s: number;
  errors: string[];
}

export interface SchedulerHistoryItem {
  id: number;
  started_at: string;
  completed_at: string | null;
  keywords_scanned: number;
  new_seeds_found: number;
  mode: string;
  status: string;
  error_msg: string | null;
}
