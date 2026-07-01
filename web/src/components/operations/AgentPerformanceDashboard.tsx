/* ───────────────────────────────────────────────────────────────────────────
 * AgentPerformanceDashboard — aggregate planner performance metrics.
 *
 * Shows strategy win rates, confidence calibration, accuracy trends,
 * duration/risk accuracy, replan metrics, and failure analysis.
 * ─────────────────────────────────────────────────────────────────────────── */
'use client';

import { useState, useEffect, useCallback } from 'react';
import { analytics } from '@jarvis/sdk';
import type { PlannerPerformance, StrategyWinRate, AccuracyTrend } from '@jarvis/sdk';

// ── Helpers ─────────────────────────────────────────────────────────────────

function fmt(v: number | null | undefined, d = '—'): string {
  if (v == null) return d;
  return `${Math.round(v * 100)}%`;
}

// ── Sub-components ─────────────────────────────────────────────────────────

function MetricCard({ label, value, color, sub, children }: { label: string; value: string; color?: string; sub?: string; children?: React.ReactNode }) {
  return (
    <div style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '14px 16px' }}>
      <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: color || 'var(--j-text)' }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: 'var(--j-text-dim)', marginTop: 2 }}>{sub}</div>}
      {children && <div style={{ marginTop: 4 }}>{children}</div>}
    </div>
  );
}

function WinRateBar({ rate, label }: { rate: number; label: string }) {
  const pct = Math.round(rate * 100);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, marginBottom: 4 }}>
      <span style={{ width: 110, textAlign: 'right', color: 'var(--j-text-dim)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
      <div style={{ flex: 1, height: 14, borderRadius: 3, background: 'rgba(255,255,255,0.05)', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', borderRadius: 3, background: pct >= 70 ? '#22c55e' : pct >= 40 ? '#f5c842' : '#ef4444', transition: 'width 0.5s' }} />
      </div>
      <span style={{ width: 36, textAlign: 'right', fontWeight: 600 }}>{pct}%</span>
    </div>
  );
}

function CalibrationDot({ bucket, error }: { bucket: string; error: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10, marginBottom: 3 }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: error <= 0.1 ? '#22c55e' : error <= 0.2 ? '#f5c842' : '#ef4444', flexShrink: 0 }} />
      <span style={{ width: 60, color: 'var(--j-text-dim)' }}>{bucket}</span>
      <span style={{ fontWeight: 500 }}>err: {Math.round(error * 100)}%</span>
    </div>
  );
}

function TrendArrow({ direction }: { direction: string }) {
  if (direction === 'improving') return <span style={{ color: '#22c55e' }}>&uarr;</span>;
  if (direction === 'declining') return <span style={{ color: '#ef4444' }}>&darr;</span>;
  return <span style={{ color: '#f5c842' }}>&rarr;</span>;
}

// ── Main Component ─────────────────────────────────────────────────────────

export function AgentPerformanceDashboard() {
  const [data, setData] = useState<PlannerPerformance | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await analytics.plannerPerformance();
      setData(result);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="hud-panel" style={{ padding: 20 }}>
        <h2 className="hud-title" style={{ margin: 0, marginBottom: 12 }}>Planner Performance</h2>
        <div style={{ padding: 20, textAlign: 'center', color: 'var(--j-text-dim)', fontSize: 12 }}>Loading metrics...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="hud-panel" style={{ padding: 20 }}>
        <h2 className="hud-title" style={{ margin: 0, marginBottom: 12 }}>Planner Performance</h2>
        <div style={{ padding: 12, borderRadius: 4, background: 'rgba(239,68,68,0.1)', color: '#ef4444', fontSize: 12 }}>{error}</div>
      </div>
    );
  }

  if (!data) return null;

  const { overall, strategy_win_rates: winRates, accuracy_trend: trend, confidence_calibration: calib,
    duration_accuracy: durAcc, risk_accuracy: riskAcc, replan_metrics: replanMetrics, failure_analysis: failures } = data;

  return (
    <div className="hud-panel" style={{ padding: 20 }}>
      {/* ── Header ────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 className="hud-title" style={{ margin: 0 }}>Planner Performance</h2>
        <button onClick={load} style={{ padding: '4px 10px', fontSize: 10, borderRadius: 3, border: '1px solid var(--j-border)', background: 'var(--j-surface)', color: 'var(--j-text)', cursor: 'pointer' }}>
          Refresh
        </button>
      </div>

      {/* ── Top-level metrics row ─────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 8, marginBottom: 16 }}>
        <MetricCard label="Total Plans" value={String(overall.total_plans)} />
        <MetricCard label="Completed" value={String(overall.completed_plans)} />
        <MetricCard label="Success Rate" value={fmt(overall.success_rate)} color={overall.success_rate >= 0.7 ? '#22c55e' : overall.success_rate >= 0.4 ? '#f5c842' : '#ef4444'} sub={`${overall.successful} ok / ${overall.failed} failed`} />
        <MetricCard label="Accuracy" value={fmt(overall.avg_prediction_accuracy)} color={overall.avg_prediction_accuracy != null && overall.avg_prediction_accuracy >= 0.7 ? '#22c55e' : '#f5c842'} />
        <MetricCard label="Accuracy Trend" value={trend.direction || 'stable'} sub={`early: ${fmt(trend.early_avg)} / recent: ${fmt(trend.recent_avg)}`}>
          <TrendArrow direction={trend.direction} />
        </MetricCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
        {/* ── Strategy Win Rates ────────────────────────────────────── */}
        <div style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '12px 14px' }}>
          <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 8 }}>Strategy Win Rates</div>
          {winRates.length > 0 ? (
            winRates.map((s: StrategyWinRate) => (
              <div key={s.strategy} style={{ marginBottom: 4 }}>
                <WinRateBar rate={s.win_rate} label={s.strategy.replace(/_/g, ' ')} />
                <div style={{ fontSize: 9, color: 'var(--j-text-dim)', paddingLeft: 118, marginTop: -2, marginBottom: 4 }}>
                  {s.successful}/{s.total} wins
                </div>
              </div>
            ))
          ) : (
            <div style={{ fontSize: 11, color: 'var(--j-text-dim)' }}>No strategy data yet</div>
          )}
        </div>

        {/* ── Confidence Calibration ────────────────────────────────── */}
        <div style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '12px 14px' }}>
          <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 6 }}>Confidence Calibration</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span style={{ fontSize: 11, color: calib.status === 'well_calibrated' ? '#22c55e' : calib.status === 'moderately_calibrated' ? '#f5c842' : calib.status === 'poorly_calibrated' ? '#ef4444' : 'var(--j-text-dim)' }}>
              {calib.status?.replace(/_/g, ' ')}
            </span>
            {calib.avg_calibration_error != null && (
              <span style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>avg err: {Math.round(calib.avg_calibration_error * 100)}%</span>
            )}
          </div>
          {calib.buckets && calib.buckets.length > 0 ? (
            calib.buckets.map((b) => <CalibrationDot key={b.bucket} bucket={b.bucket} error={b.error} />)
          ) : (
            <div style={{ fontSize: 11, color: 'var(--j-text-dim)' }}>No calibration data</div>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
        {/* ── Duration & Risk Accuracy ──────────────────────────────── */}
        <div style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '12px 14px' }}>
          <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 8 }}>Duration Accuracy</div>
          {durAcc.status !== 'no_data' ? (
            <>
              <div style={{ fontSize: 11, marginBottom: 4 }}>
                Status: <span style={{ color: durAcc.status === 'good' ? '#22c55e' : durAcc.status === 'moderate' ? '#f5c842' : '#ef4444', fontWeight: 600 }}>{durAcc.status}</span>
              </div>
              <div style={{ fontSize: 10, color: 'var(--j-text-dim)', marginBottom: 2 }}>Avg error: {Math.round(durAcc.avg_duration_error * 100)}%</div>
              <div style={{ fontSize: 10, color: 'var(--j-text-dim)', marginBottom: 2 }}>Plans with data: {durAcc.plans_with_duration_data}</div>
              {durAcc.significantly_wrong > 0 && (
                <div style={{ fontSize: 10, color: '#f5c842' }}>{durAcc.significantly_wrong} plans off by &gt;25%</div>
              )}
            </>
          ) : (
            <div style={{ fontSize: 11, color: 'var(--j-text-dim)' }}>No data</div>
          )}
        </div>

        <div style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '12px 14px' }}>
          <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 8 }}>Risk Accuracy</div>
          <div style={{ fontSize: 11, marginBottom: 4 }}>
            Discrimination: <span style={{ color: riskAcc.discrimination_quality === 'good' ? '#22c55e' : '#f5c842', fontWeight: 600 }}>{riskAcc.discrimination_quality}</span>
          </div>
          <div style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>
            High-risk fail rate: {Math.round(riskAcc.high_risk_failure_rate * 100)}% ({riskAcc.high_risk_plans} plans)
          </div>
          <div style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>
            Low-risk fail rate: {Math.round(riskAcc.low_risk_failure_rate * 100)}% ({riskAcc.low_risk_plans} plans)
          </div>
        </div>
      </div>

      {/* ── Replan & Failure Analysis ───────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '12px 14px' }}>
          <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 8 }}>Replan Metrics</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, fontSize: 11 }}>
            <span style={{ color: 'var(--j-text-dim)' }}>Replanned</span><span>{replanMetrics.replanned_count} / {replanMetrics.total_plans}</span>
            <span style={{ color: 'var(--j-text-dim)' }}>Replan Rate</span><span>{Math.round(replanMetrics.replan_rate * 100)}%</span>
            <span style={{ color: 'var(--j-text-dim)' }}>Avg Replans/Plan</span><span>{replanMetrics.avg_replans_per_plan}</span>
            <span style={{ color: 'var(--j-text-dim)' }}>Improved After</span><span>{replanMetrics.improved_after_replan}</span>
          </div>
        </div>

        <div style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '12px 14px' }}>
          <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 8 }}>Failure Analysis</div>
          {failures?.total_failures > 0 ? (
            <>
              <div style={{ fontSize: 11, color: '#ef4444', fontWeight: 600, marginBottom: 6 }}>{failures.total_failures} failed plans</div>
              {failures.common_reasons?.length > 0 && (
                <div style={{ fontSize: 10 }}>
                  {failures.common_reasons.map((r) => (
                    <div key={r.reason} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                      <span style={{ color: 'var(--j-text-dim)' }}>{r.reason.replace(/_/g, ' ')}</span>
                      <span style={{ fontWeight: 500 }}>{r.count}x</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div style={{ fontSize: 11, color: 'var(--j-text-dim)' }}>No failures recorded</div>
          )}
        </div>
      </div>
    </div>
  );
}
