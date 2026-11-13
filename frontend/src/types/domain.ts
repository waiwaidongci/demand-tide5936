export interface User {id:number;name:string;email:string;role:string}
export interface Series {id:number;code:string;name:string;city:string;product:string;unit:string;source_file:string;observation_count:number;total_demand:number}
export interface Observation {id:number;series_id:number;day:string;value:number}
export interface ForecastPoint {day:string;predicted:number;lower:number;upper:number}
export interface SegmentRow {lead_day:number;actual:number;predicted:number;error:number;abs_error:number}
export interface BacktestSegment {origin_index:number;start_index:number;end_index:number;segment_mae:number;segment_wape:number|null;predictions:SegmentRow[]}
export interface LeadMetric {lead_day:number;mae:number;wape:number|null;samples:number}
export interface Comparison {model:string;alpha:number|null;mae:number;wape:number|null;lead_metrics?:LeadMetric[]}
export type BacktestMode='multi_step'|'one_step';
export interface MultiStepResult {
  backtest_mode:'multi_step';
  selected:Comparison;
  comparisons:Comparison[];
  lead_metrics:LeadMetric[];
  backtest_segments:BacktestSegment[];
  segment_count:number;
  horizon:number;
  validation_days:number;
  training_days:number;
  min_training_days:number;
  interval_note:string;
}
export interface LegacyResult {
  backtest_mode?:'one_step';
  selected:Comparison;
  comparisons:Comparison[];
  validation_days:number;
  training_days:number;
  interval_note:string;
}
export type RunResult=MultiStepResult|LegacyResult;
export interface Run {id:number;name:string;series_id:number;horizon:number;season:number;status:string;error:string|null;created_at:string;result?:RunResult;points?:ForecastPoint[];series?:Series}
export interface Release {id:number;run_id:number;note:string;published_at:string}
export interface Audit {id:number;actor:string;action:string;target:string;created_at:string}
