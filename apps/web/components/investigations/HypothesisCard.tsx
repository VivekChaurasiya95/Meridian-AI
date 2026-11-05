"use client";

import * as React from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { MeridianApiError, formatTimestamp, reviewHypothesis } from "@/lib/api";
import type { Hypothesis, HypothesisVerdict } from "@/lib/types";

const VERDICT_LABEL: Record<HypothesisVerdict, string> = {
  useful: "Useful",
  rejected: "Rejected",
  needs_evidence: "Needs evidence",
};

const VERDICT_TONE: Record<HypothesisVerdict, BadgeTone> = {
  useful: "success",
  rejected: "danger",
  needs_evidence: "warning",
};

const VERDICTS: HypothesisVerdict[] = ["useful", "rejected", "needs_evidence"];

/** One hypothesis with user review controls and review history (M7). */
export function HypothesisCard({
  hypothesis,
  onReviewed,
}: {
  hypothesis: Hypothesis;
  onReviewed: () => void;
}) {
  const [formOpen, setFormOpen] = React.useState(false);
  const [verdict, setVerdict] = React.useState<HypothesisVerdict>("useful");
  const [note, setNote] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const reviews = hypothesis.reviews;
  const latest = reviews.length > 0 ? reviews[reviews.length - 1] : null;

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await reviewHypothesis(hypothesis.id, {
        verdict,
        note: note.trim() === "" ? undefined : note.trim(),
      });
      setFormOpen(false);
      setNote("");
      onReviewed();
    } catch (err) {
      if (err instanceof MeridianApiError && err.status === 403) {
        setError("Your role cannot submit reviews. Reviews need a contributor role.");
      } else {
        setError(err instanceof Error ? err.message : "Could not record the review.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="flex flex-col gap-2 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="neutral" dot={false}>
          {hypothesis.status}
        </Badge>
        {latest !== null && (
          <Badge tone={VERDICT_TONE[latest.verdict]} dot={false}>
            {VERDICT_LABEL[latest.verdict]}
          </Badge>
        )}
        <span className="text-[14px] font-semibold">{hypothesis.title}</span>
        {hypothesis.confidence !== null && (
          <span className="ml-auto font-mono text-xs text-ink-3">
            confidence {hypothesis.confidence.toFixed(2)}
          </span>
        )}
      </div>
      <p className="text-[13px] text-ink-2">{hypothesis.description}</p>
      {hypothesis.links.evidence.length > 0 && (
        <p className="font-mono text-[11px] text-ink-3">
          {hypothesis.links.evidence
            .map((link) => `${link.relationship}: ${link.kind}`)
            .join(" · ")}
        </p>
      )}
      {latest !== null && (
        <p className="text-[12px] text-ink-3">
          Latest review: {VERDICT_LABEL[latest.verdict].toLowerCase()}
          {latest.note !== null && ` — ${latest.note}`} ·{" "}
          {formatTimestamp(latest.created_at)}
        </p>
      )}
      {reviews.length > 1 && (
        <details className="text-[12px]">
          <summary className="cursor-pointer font-semibold text-ink-2 hover:text-ink">
            Review history ({reviews.length})
          </summary>
          <ol className="mt-1.5 flex flex-col gap-1 border-l-2 border-line pl-3">
            {reviews.map((review, index) => (
              <li key={review.id} className="flex flex-wrap items-center gap-2 text-ink-2">
                <Badge tone={VERDICT_TONE[review.verdict]} dot={false}>
                  {VERDICT_LABEL[review.verdict]}
                </Badge>
                {review.note !== null && <span className="min-w-0 flex-1">{review.note}</span>}
                <span className="font-mono text-[11px] text-ink-3">
                  {formatTimestamp(review.created_at)}
                  {index === reviews.length - 1 && " · latest"}
                </span>
              </li>
            ))}
          </ol>
        </details>
      )}
      {error !== null && (
        <Alert tone="danger" title="Review failed">
          {error}
        </Alert>
      )}
      {formOpen ? (
        <form onSubmit={onSubmit} className="flex flex-col gap-2.5 border-t border-line/60 pt-3">
          <fieldset className="flex flex-wrap gap-2">
            <legend className="sr-only">Verdict</legend>
            {VERDICTS.map((option) => (
              <label
                key={option}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-[10px] border border-line bg-surface-1 px-3 py-1.5 text-[13px] font-semibold text-ink-2 transition-colors has-checked:border-accent has-checked:text-ink"
              >
                <input
                  type="radio"
                  name={`verdict-${hypothesis.id}`}
                  value={option}
                  checked={verdict === option}
                  onChange={() => setVerdict(option)}
                  className="accent-[var(--color-accent)]"
                />
                {VERDICT_LABEL[option]}
              </label>
            ))}
          </fieldset>
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor={`review-note-${hypothesis.id}`}
              className="text-[13px] font-semibold text-ink"
            >
              Note (optional)
            </label>
            <textarea
              id={`review-note-${hypothesis.id}`}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Why is this useful, or what evidence is missing?"
              rows={2}
              maxLength={500}
              className="w-full rounded-[10px] border border-line bg-surface-1 px-3.5 py-2.5 text-[14px] text-ink outline-none placeholder:text-ink-3 hover:border-line-strong focus:border-accent"
            />
          </div>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={submitting}>
              {submitting ? "Recording…" : "Record review"}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => {
                setFormOpen(false);
                setError(null);
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div>
          <Button size="sm" variant="secondary" onClick={() => setFormOpen(true)}>
            Review
          </Button>
        </div>
      )}
    </Card>
  );
}
