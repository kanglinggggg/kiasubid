import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  Clipboard,
  LoaderCircle,
  MessageSquareText,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { tenderLabApi } from "../api/client";
import type {
  ProposalAnswerKey,
  ProposalAnswerReviewResponse,
  ProposalCritique,
  ProposalDraftResponse,
  ProposalPlanResponse,
  TenderLabRequest,
  TenderLabStartupAnswers,
} from "../types/tenderLab";

interface GuidedProposalBuilderProps {
  tender: TenderLabRequest;
  onUseDraft: (markdown: string, answers: TenderLabStartupAnswers) => Promise<void>;
}

const EMPTY_ANSWERS: TenderLabStartupAnswers = {
  solution_summary: "",
  technical_architecture: "",
  delivery_approach: "",
  operations_maintenance: "",
  security_approach: "",
  risk_management: "",
  team_strength: "",
  social_value: "",
};

export function GuidedProposalBuilder({ tender, onUseDraft }: GuidedProposalBuilderProps) {
  const [plan, setPlan] = useState<ProposalPlanResponse | null>(null);
  const [answers, setAnswers] = useState<TenderLabStartupAnswers>({
    ...EMPTY_ANSWERS,
    ...tender.startup_answers,
  });
  const [reviews, setReviews] = useState<Record<string, ProposalAnswerReviewResponse>>({});
  const [skippedQuestionIds, setSkippedQuestionIds] = useState<string[]>([]);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [loading, setLoading] = useState<"plan" | "review" | "draft" | "use" | null>("plan");
  const [draft, setDraft] = useState<ProposalDraftResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reviewRequest = useRef(0);
  const draftRequest = useRef(0);

  useEffect(() => {
    let cancelled = false;
    reviewRequest.current += 1;
    draftRequest.current += 1;
    setLoading("plan");
    setError(null);
    setPlan(null);
    // Keep the user's answers, but source edits invalidate old critique and drafts.
    setReviews({});
    setDraft(null);
    setSkippedQuestionIds([]);
    setQuestionIndex(0);
    tenderLabApi
      .proposalPlan(tender)
      .then((value) => {
        if (!cancelled) setPlan(value);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "Unable to start the mentor interview.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(null);
      });
    return () => {
      cancelled = true;
    };
  }, [tender.agency, tender.source_label, tender.tender_text, tender.tender_title]);

  const currentQuestion = plan?.questions[questionIndex] ?? null;
  const currentReview = currentQuestion ? reviews[currentQuestion.id] : null;
  const completedCount = plan
    ? plan.questions.filter(
        (question) => reviews[question.id] || skippedQuestionIds.includes(question.id),
      ).length
    : 0;
  const riskyReviews = Object.values(reviews).filter(
    (review) => review.critique.verdict === "RISKY_CLAIM",
  );
  const canGenerate = useMemo(
    () =>
      Boolean(
        plan &&
          plan.questions
            .filter((question) => question.required)
            .every(
              (question) =>
                answers[question.answer_key].trim().length >= 2 &&
                reviews[question.id] &&
                reviews[question.id].critique.verdict !== "RISKY_CLAIM",
            ),
      ),
    [answers, plan, reviews],
  );

  function tenderWithAnswers(): TenderLabRequest {
    return { ...tender, startup_answers: answers };
  }

  function updateAnswer(key: ProposalAnswerKey, value: string, questionId: string) {
    reviewRequest.current += 1;
    draftRequest.current += 1;
    setAnswers((current) => ({ ...current, [key]: value }));
    setSkippedQuestionIds((current) => current.filter((id) => id !== questionId));
    setReviews((current) => {
      const next = { ...current };
      delete next[questionId];
      return next;
    });
    setDraft(null);
  }

  async function reviewAnswer() {
    if (!currentQuestion) return;
    const answer = answers[currentQuestion.answer_key].trim();
    if (answer.length < 2) return;
    const requestId = ++reviewRequest.current;
    setLoading("review");
    setError(null);
    try {
      const response = await tenderLabApi.reviewProposalAnswer(
        tenderWithAnswers(),
        currentQuestion.id,
        answer,
      );
      if (reviewRequest.current === requestId) {
        setReviews((current) => ({ ...current, [currentQuestion.id]: response }));
      }
    } catch (reason) {
      if (reviewRequest.current === requestId) {
        setError(reason instanceof Error ? reason.message : "Unable to review this answer.");
      }
    } finally {
      if (reviewRequest.current === requestId) setLoading(null);
    }
  }

  function nextQuestion() {
    if (!plan) return;
    setQuestionIndex((current) => Math.min(current + 1, plan.questions.length));
  }

  function skipOptionalQuestion() {
    if (!currentQuestion || currentQuestion.required) return;
    setSkippedQuestionIds((current) =>
      current.includes(currentQuestion.id) ? current : [...current, currentQuestion.id],
    );
    nextQuestion();
  }

  async function generateDraft() {
    if (!canGenerate) return;
    const requestId = ++draftRequest.current;
    setLoading("draft");
    setError(null);
    try {
      const response = await tenderLabApi.generateProposalDraft(tenderWithAnswers());
      if (draftRequest.current === requestId) setDraft(response);
    } catch (reason) {
      if (draftRequest.current === requestId) {
        setError(reason instanceof Error ? reason.message : "Unable to generate the proposal draft.");
      }
    } finally {
      if (draftRequest.current === requestId) setLoading(null);
    }
  }

  async function copyDraft() {
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(draft.markdown);
    } catch {
      setError("The browser blocked clipboard access. Select the draft text manually.");
    }
  }

  async function useDraft() {
    if (!draft) return;
    setLoading("use");
    setError(null);
    try {
      await onUseDraft(draft.markdown, answers);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to place the draft in Agent Room.");
    } finally {
      setLoading(null);
    }
  }

  if (loading === "plan" && !plan) {
    return (
      <section className="tender-lab-card proposal-studio-loading" aria-live="polite">
        <LoaderCircle className="spin" size={20} />
        <div><h4>Mentor is planning the interview</h4><p>Questions stay tied to this tender workspace</p></div>
      </section>
    );
  }

  if (!plan) {
    return (
      <section className="tender-lab-card proposal-studio-error" role="alert">
        <AlertTriangle size={20} /><div><h4>Mentor interview could not start</h4><p>{error}</p></div>
      </section>
    );
  }

  return (
    <div className="proposal-studio-stack">
      <section className="tender-lab-card proposal-studio-hero">
        <div className="tender-lab-card-title">
          <MessageSquareText size={18} />
          <div><span>B2 · Guided Proposal Builder</span><h4>Founder interview → grounded draft</h4></div>
          <span className="proposal-studio-progress">{completedCount}/{plan.questions.length}</span>
        </div>
        <p>{plan.mentor_intro}</p>
        <div className="proposal-studio-steps" aria-label="Proposal mentor questions">
          {plan.questions.map((question, index) => (
            <button
              aria-current={questionIndex === index ? "step" : undefined}
              className={reviews[question.id] ? reviews[question.id].critique.verdict.toLowerCase() : ""}
              key={question.id}
              onClick={() => setQuestionIndex(index)}
              type="button"
            >
              {reviews[question.id] ? <Check size={12} /> : index + 1}
              <span>{question.section}</span>
            </button>
          ))}
        </div>
        <p className="tender-lab-method">{plan.boundary}</p>
      </section>

      {error && (
        <div className="tender-lab-alert error" role="alert">
          <AlertTriangle size={16} /><span>{error}</span><button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {currentQuestion ? (
        <section className="tender-lab-card proposal-studio-question">
          <div className="proposal-studio-question-head">
            <div>
              <span>{currentQuestion.required ? "Required" : "Optional"} · {currentQuestion.section}</span>
              <h4>{currentQuestion.question}</h4>
            </div>
            <small>{questionIndex + 1} / {plan.questions.length}</small>
          </div>
          <p className="proposal-studio-why"><ShieldCheck size={14} /> {currentQuestion.why_it_matters}</p>
          <ul>{currentQuestion.answer_guidance.map((item) => <li key={item}>{item}</li>)}</ul>
          <textarea
            aria-label={`${currentQuestion.section} answer`}
            disabled={loading !== null}
            onChange={(event) => updateAnswer(currentQuestion.answer_key, event.target.value, currentQuestion.id)}
            placeholder="Explain it naturally  the mentor will help structure it"
            value={answers[currentQuestion.answer_key]}
          />
          <div className="proposal-studio-actions">
            <button
              className="tender-lab-secondary"
              disabled={questionIndex === 0 || loading !== null}
              onClick={() => setQuestionIndex((current) => Math.max(0, current - 1))}
              type="button"
            ><ArrowLeft size={14} /> Previous</button>
            <button
              className="tender-lab-agent-run"
              disabled={answers[currentQuestion.answer_key].trim().length < 2 || loading !== null}
              onClick={() => void reviewAnswer()}
              type="button"
            >
              {loading === "review" ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />}
              {currentReview ? "Review revision" : "Review answer"}
            </button>
            {!currentQuestion.required && !answers[currentQuestion.answer_key].trim() && (
              <button className="tender-lab-secondary" disabled={loading !== null} onClick={skipOptionalQuestion} type="button">
                Skip optional <ArrowRight size={14} />
              </button>
            )}
          </div>

          {currentReview && <CritiqueCard review={currentReview} />}
          {currentReview && currentReview.critique.verdict !== "RISKY_CLAIM" && (
            <button className="proposal-studio-next" onClick={nextQuestion} type="button">
              {questionIndex === plan.questions.length - 1 ? "Finish interview" : "Continue"} <ArrowRight size={14} />
            </button>
          )}
        </section>
      ) : (
        <section className="tender-lab-card proposal-studio-ready">
          <Check size={20} />
          <div>
            <h4>Interview complete</h4>
            <p>{canGenerate ? "The required answers are reviewed and ready for a grounded draft." : "Return to any incomplete or risky answer before generating."}</p>
          </div>
          <button className="tender-lab-agent-run" disabled={!canGenerate || loading !== null} onClick={() => void generateDraft()} type="button">
            {loading === "draft" ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />}
            Generate grounded draft
          </button>
        </section>
      )}

      {questionIndex < plan.questions.length && canGenerate && (
        <section className="tender-lab-card proposal-studio-generate">
          <div><strong>Enough grounded answers collected</strong><span>You can generate now or review the optional section first</span></div>
          <button className="tender-lab-agent-run" disabled={loading !== null} onClick={() => void generateDraft()} type="button">
            {loading === "draft" ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />}
            Generate grounded draft
          </button>
        </section>
      )}

      {riskyReviews.length > 0 && (
        <section className="tender-lab-card proposal-studio-risk">
          <AlertTriangle size={18} /><p>Revise {riskyReviews.length} unsafe certainty claim{riskyReviews.length === 1 ? "" : "s"} before drafting.</p>
        </section>
      )}

      {draft && (
        <section className="tender-lab-card proposal-studio-draft">
          <div className="tender-lab-card-title">
            <Clipboard size={18} />
            <div><span>Grounded preparation draft</span><h4>{draft.title}</h4></div>
            <span className={`tender-lab-provider-state ${draft.provider_state.toLowerCase()}`}>{draft.provider_state}</span>
          </div>
          <div className="proposal-studio-draft-document">
            <h5>Executive Summary</h5>
            <p>{draft.executive_summary}</p>
            {draft.sections.map((section) => (
              <article key={section.section_key}>
                <h5>{section.heading}</h5>
                <p>{section.text}</p>
                <small>Grounded in {section.supporting_answer_keys.map((key) => key.replaceAll("_", " ")).join(", ")}</small>
              </article>
            ))}
            {draft.open_items.length > 0 && <details><summary>Open items for human review · {draft.open_items.length}</summary><ul>{draft.open_items.map((item) => <li key={item}>{item}</li>)}</ul></details>}
          </div>
          {draft.fallback_reason && (
            <p className="tender-lab-method">Prepared with the policy rules engine · {draft.fallback_reason}</p>
          )}
          <p className="proposal-studio-review-notice"><AlertTriangle size={14} /> {draft.review_notice}</p>
          <div className="proposal-studio-actions">
            <button className="tender-lab-secondary" onClick={() => void copyDraft()} type="button"><Clipboard size={14} /> Copy draft</button>
            <button className="tender-lab-agent-run" disabled={loading !== null} onClick={() => void useDraft()} type="button">
              {loading === "use" ? <LoaderCircle className="spin" size={15} /> : <ArrowRight size={15} />}
              Use draft in Agent Room
            </button>
          </div>
          <p className="tender-lab-method">{draft.boundary}</p>
        </section>
      )}
    </div>
  );
}

function CritiqueCard({ review }: { review: ProposalAnswerReviewResponse }) {
  const critique: ProposalCritique = review.critique;
  return (
    <article className={`proposal-studio-critique ${critique.verdict.toLowerCase()}`} aria-live="polite">
      <div>
        <span>{critique.verdict.replaceAll("_", " ")}</span>
        <small>{review.execution.mode.replaceAll("_", " ")}</small>
      </div>
      <h5>{critique.mentor_feedback}</h5>
      {critique.strengths.length > 0 && <ul className="strengths">{critique.strengths.map((item) => <li key={item}>{item}</li>)}</ul>}
      {critique.gaps.length > 0 && <ul>{critique.gaps.map((item) => <li key={item}>{item}</li>)}</ul>}
      {critique.follow_up_question && <p><strong>Mentor follow-up</strong>{critique.follow_up_question}</p>}
      {critique.formalized_answer && critique.verdict !== "RISKY_CLAIM" && <details open><summary>Structured response wording</summary><p>{critique.formalized_answer}</p><small>Draft wording only  Verify factual claims and evidence before use</small></details>}
      {critique.evidence_needed.length > 0 && <details><summary>Evidence to attach</summary><ul>{critique.evidence_needed.map(item => <li key={item}>{item}</li>)}</ul></details>}
      {review.fallback_reason && <small>Review completed with the policy rules engine</small>}
    </article>
  );
}
