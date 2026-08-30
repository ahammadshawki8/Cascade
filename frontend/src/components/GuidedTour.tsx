"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { X, ArrowRight, Loader2 } from "lucide-react";
import type { TourStep } from "./tourSteps";
import styles from "./GuidedTour.module.css";

/**
 * A walkthrough that waits for the system, not for a Next button.
 *
 * The previous guide was three static labels that lit up after the fact. It
 * could not be wrong, because it never claimed anything — and it taught
 * nothing for the same reason.
 *
 * This one is built on two rules:
 *
 *   1. A step ends when the app *actually does the thing*. Not on a timer, not
 *      on a click. If the compile has not landed, the tour is still on that
 *      step, because the tour is describing reality rather than narrating over
 *      it.
 *
 *   2. Only the highlighted control is clickable. Everything else is covered.
 *      A walkthrough you can wander out of is a walkthrough that ends with the
 *      viewer somewhere confusing, blaming the product.
 */

/** Where the hole is, in viewport coordinates. */
interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

const PAD = 6;

export function GuidedTour({
  steps,
  index,
  waiting,
  preparing = false,
  onAdvance,
  onCancel,
}: {
  steps: TourStep[];
  index: number;
  /** True while the step's completion event has not fired yet. */
  waiting: boolean;
  /** The world is still being reset; nothing is safe to click yet. */
  preparing?: boolean;
  onAdvance: () => void;
  onCancel: () => void;
}) {
  const step = steps[index];
  const target = step?.target;
  const [rect, setRect] = useState<Rect | null>(null);
  const [cardH, setCardH] = useState(CARD_H);
  const frame = useRef<number | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  /**
   * How long this step has been waiting.
   *
   * A cold run against Bedrock is fifteen to thirty seconds, and a spinner with
   * no number attached is indistinguishable from a hang after about eight of
   * them. Showing the count turns "is this broken?" into "it is working, this
   * one is slow", which is the difference between waiting and giving up.
   */
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    setElapsed(0);
    if (!waiting) return;
    const started = Date.now();
    const timer = setInterval(
      () => setElapsed(Math.round((Date.now() - started) / 1000)),
      1000
    );
    return () => clearInterval(timer);
  }, [waiting, index]);

  // Long enough that it never appears on a healthy run, short enough that
  // nobody sits staring at a dead card.
  const stuck = waiting && elapsed >= 45;

  /**
   * The target moves: panels re-render, lists grow, the island slides in. So
   * the hole is re-measured continuously rather than once per step — a
   * spotlight pointing at where a button *used to be* is worse than no
   * spotlight at all.
   */
  const measure = useCallback(() => {
    // The caption is not a fixed height — the copy varies by step — so its own
    // box decides the clamp. Guessing produced a card whose footer, the part
    // telling you what to do, sat below the fold.
    if (cardRef.current) {
      const h = cardRef.current.offsetHeight;
      if (h > 0) setCardH((prev) => (Math.abs(prev - h) > 1 ? h : prev));
    }
    if (!target) {
      setRect(null);
      return;
    }
    // A step may name several candidates in priority order: the policy step
    // starts on the rule row and moves to the commit dialog the moment it
    // opens, because the spotlight blocks everything it does not cover and the
    // user has to be able to reach the field and the button inside it.
    const selectors = Array.isArray(target) ? target : [target];
    let r: DOMRect | null = null;
    for (const selector of selectors) {
      for (const el of Array.from(document.querySelectorAll(selector))) {
        const box = el.getBoundingClientRect();
        if (box.width > 0 || box.height > 0) {
          r = box;
          break;
        }
      }
      if (r) break;
    }
    if (!r) {
      setRect(null);
      return;
    }
    setRect({
      top: r.top - PAD,
      left: r.left - PAD,
      width: r.width + PAD * 2,
      height: r.height + PAD * 2,
    });
  }, [target]);

  useEffect(() => {
    const loop = () => {
      measure();
      frame.current = requestAnimationFrame(loop);
    };
    frame.current = requestAnimationFrame(loop);
    return () => {
      if (frame.current) cancelAnimationFrame(frame.current);
    };
  }, [measure]);

  // Escape leaves the tour. Anyone trapped in a walkthrough will reach for it.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  if (!step) return null;

  const vw = typeof window === "undefined" ? 1440 : window.innerWidth;
  const vh = typeof window === "undefined" ? 900 : window.innerHeight;

  // The card sits beside the hole, flipping whenever it would run off screen.
  const card = placeCard(rect, vw, vh, cardH);

  return (
    <div className={styles.root}>
      {/* Four panels rather than one clipped element: this dims *and* blocks,
          and the arithmetic is legible enough to debug at a glance. */}
      {rect ? (
        <>
          <div
            className={styles.shade}
            style={{ top: 0, left: 0, width: "100%", height: Math.max(rect.top, 0) }}
            onClick={swallow}
          />
          <div
            className={styles.shade}
            style={{
              top: rect.top,
              left: 0,
              width: Math.max(rect.left, 0),
              height: rect.height,
            }}
            onClick={swallow}
          />
          <div
            className={styles.shade}
            style={{
              top: rect.top,
              left: rect.left + rect.width,
              width: Math.max(vw - rect.left - rect.width, 0),
              height: rect.height,
            }}
            onClick={swallow}
          />
          <div
            className={styles.shade}
            style={{
              top: rect.top + rect.height,
              left: 0,
              width: "100%",
              height: Math.max(vh - rect.top - rect.height, 0),
            }}
            onClick={swallow}
          />
          <div
            className={styles.ring}
            style={{
              top: rect.top,
              left: rect.left,
              width: rect.width,
              height: rect.height,
            }}
          />
        </>
      ) : (
        // No target on this step, or it has not rendered yet: cover everything.
        <div className={styles.shadeAll} onClick={swallow} />
      )}

      <div
        ref={cardRef}
        className={`${styles.card} ${styles[card.side]}`}
        style={{ top: card.top, left: card.left }}
        role="dialog"
        aria-label={`Walkthrough step ${index + 1}`}
      >
        <div className={styles.head}>
          <span className={styles.count}>
            {index + 1}
            <span className={styles.of}> / {steps.length}</span>
          </span>
          <span className={styles.title}>{step.title}</span>
          <button className={styles.close} onClick={onCancel} aria-label="Leave the walkthrough">
            <X size={14} />
          </button>
        </div>

        <div className={styles.body}>
          <Rich text={step.body} />
        </div>

        {/* The mechanism underneath, kept visually distinct from the
            instruction. The instruction is what to do; this is why the project
            exists, and merging the two makes both skimmable-past. */}
        {step.mechanism && (
          <div className={styles.mechanism}>
            <Rich text={step.mechanism} />
          </div>
        )}

        {/* The instruction and the wait are shown together rather than one
            replacing the other. A step can ask you to look at something *while*
            the system works, and hiding the instruction the moment it starts
            working means you never see what you were meant to do. */}
        <div className={styles.foot}>
          {step.advanceOn ? (
            <span className={styles.actions}>
              <span className={styles.doIt}>
                {step.action ?? "Click the highlighted control"}
              </span>
              {waiting && (
                <span className={styles.waiting}>
                  <Loader2 size={13} className={styles.spin} />
                  {step.waitingLabel ?? "Waiting for that to finish"}
                  {elapsed >= 15 && (
                    <span className={styles.elapsed}>{elapsed}s</span>
                  )}
                </span>
              )}
              {/* The last resort. Every waiting step accepts an event that
                  fires whatever the outcome, so this should never be needed —
                  but "should never" is not a thing to leave a reviewer stranded
                  on, and a walkthrough that cannot be advanced is worse than
                  one that admits it lost the thread. */}
              {(stuck || step.optional) && (
                <button className={styles.unstick} onClick={onAdvance}>
                  {step.optional && !stuck ? "Skip this one" : "Continue anyway"}
                  <ArrowRight size={12} />
                </button>
              )}
            </span>
          ) : preparing ? (
            <span className={styles.waiting}>
              <Loader2 size={13} className={styles.spin} />
              Setting up a clean world to walk through
            </span>
          ) : (
            <button className={styles.next} onClick={onAdvance}>
              {step.nextLabel ?? "Next"}
              <ArrowRight size={13} />
            </button>
          )}
          <span className={styles.spacer} />
          <button className={styles.skip} onClick={onCancel}>
            Skip
          </button>
        </div>

        <div className={styles.progress}>
          <span
            className={styles.progressFill}
            style={{ width: `${((index + 1) / steps.length) * 100}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function swallow(e: React.MouseEvent) {
  e.preventDefault();
  e.stopPropagation();
}

/**
 * The two bits of emphasis the copy needs, tokenised rather than injected.
 *
 * The strings are ours and static, so `dangerouslySetInnerHTML` would be safe
 * here — but it would also be the only place in the app where markup arrives
 * as data, and that is a habit worth not starting.
 */
function Rich({ text }: { text: string }) {
  return (
    <>
      {text.split("\n\n").map((para, p) => (
        <p key={p} className={styles.para}>
          {para.split(/(<b>.*?<\/b>|<code>.*?<\/code>)/g).map((chunk, i) => {
            if (chunk.startsWith("<b>")) {
              return <b key={i}>{chunk.slice(3, -4)}</b>;
            }
            if (chunk.startsWith("<code>")) {
              return <code key={i}>{chunk.slice(6, -7)}</code>;
            }
            return chunk;
          })}
        </p>
      ))}
    </>
  );
}

const CARD_W = 340;
const CARD_H = 250;
const GAP = 16;

/** Beside the hole, flipped to whichever side it fits. */
function placeCard(
  rect: Rect | null,
  vw: number,
  vh: number,
  h: number
): { top: number; left: number; side: "right" | "left" | "below" | "above" | "centre" } {
  if (!rect) {
    return { top: vh / 2 - h / 2, left: vw / 2 - CARD_W / 2, side: "centre" };
  }

  const clampTop = (t: number) => Math.min(Math.max(t, 12), Math.max(vh - h - 12, 12));
  const clampLeft = (l: number) => Math.min(Math.max(l, 12), vw - CARD_W - 12);

  if (rect.left + rect.width + GAP + CARD_W < vw) {
    return {
      top: clampTop(rect.top + rect.height / 2 - h / 2),
      left: rect.left + rect.width + GAP,
      side: "right",
    };
  }
  if (rect.left - GAP - CARD_W > 0) {
    return {
      top: clampTop(rect.top + rect.height / 2 - h / 2),
      left: rect.left - GAP - CARD_W,
      side: "left",
    };
  }
  if (rect.top + rect.height + GAP + h < vh) {
    return {
      top: rect.top + rect.height + GAP,
      left: clampLeft(rect.left + rect.width / 2 - CARD_W / 2),
      side: "below",
    };
  }
  return {
    top: clampTop(rect.top - GAP - h),
    left: clampLeft(rect.left + rect.width / 2 - CARD_W / 2),
    side: "above",
  };
}
