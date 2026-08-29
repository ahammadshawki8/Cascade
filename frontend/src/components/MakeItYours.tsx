"use client";

import { Check, ArrowRight, X } from "lucide-react";
import styles from "./MakeItYours.module.css";

/**
 * The second act.
 *
 * The walkthrough proves the idea on data we shipped. That is the moment a
 * reviewer is most likely to conclude the whole thing is a scripted demo, and
 * the honest answer is three things they can do in about two minutes with their
 * own material. Each one is checked off by reading real state, not by
 * remembering that a button was pressed, so it cannot claim credit for
 * something that did not happen.
 */

export interface Progress {
  wroteRule: boolean;
  importedProcedure: boolean;
  connectedApp: boolean;
  createdKey: boolean;
}

/**
 * Ordered by friction, not by how impressive each one is.
 *
 * The first item has to be winnable in about ten seconds or people stop after
 * reading it. Importing is a paste and a click; writing a rule is a short form;
 * a key is a button but only pays off inside an editor; Slack is last because
 * it is the only one that makes you leave the app to go and fetch a webhook
 * URL. Leading with the most impressive item and burying the cheapest is how
 * checklists go unfinished.
 */
const ITEMS: {
  id: keyof Progress;
  title: string;
  body: string;
  cta: string;
  effort: string;
}[] = [
  {
    id: "importedProcedure",
    title: "Import a runbook you already have",
    body: "Paste one in, or use the example. Cascade links it to policy, and from then on it goes stale when policy moves.",
    cta: "Import one",
    effort: "10 seconds",
  },
  {
    id: "wroteRule",
    title: "Write a policy rule of your own",
    body: "Not a setting. A rule the agent has to obey, that nothing in this codebase knows about.",
    cta: "Write one",
    effort: "1 minute",
  },
  {
    id: "createdKey",
    title: "Let your own agent ask",
    body: "Create a key, paste four lines into your editor, and ask it whether what it remembers is still valid.",
    cta: "Create a key",
    effort: "2 minutes",
  },
  {
    id: "connectedApp",
    title: "Send the result to Slack",
    body: "A webhook URL is all it takes. The next refusal lands in a real channel.",
    cta: "Connect Slack",
    effort: "3 minutes",
  },
];

export function MakeItYours({
  progress,
  onGo,
  onDismiss,
}: {
  progress: Progress;
  onGo: (id: keyof Progress) => void;
  onDismiss: () => void;
}) {
  const done = ITEMS.filter((i) => progress[i.id]).length;
  const next = ITEMS.find((i) => !progress[i.id]);

  return (
    <div className={styles.card}>
      <div className={styles.head}>
        <span className={styles.title}>Make it yours</span>
        <span className={styles.progress}>
          {done} of {ITEMS.length}
        </span>
        <span className={styles.spacer} />
        <button className={styles.close} onClick={onDismiss} aria-label="Dismiss">
          <X size={13} />
        </button>
      </div>

      <p className={styles.lead}>
        Everything above runs on data that shipped with the product. These take a
        couple of minutes each and run on yours.
      </p>

      <div className={styles.items}>
        {ITEMS.map((item) => {
          const complete = progress[item.id];
          const isNext = next?.id === item.id;
          return (
            <div
              key={item.id}
              className={`${styles.item} ${complete ? styles.itemDone : ""} ${
                isNext ? styles.itemNext : ""
              }`}
            >
              <span className={styles.tick}>
                {complete && <Check size={12} strokeWidth={3} />}
              </span>
              <div className={styles.itemBody}>
                <div className={styles.itemTitle}>
                  {item.title}
                  {!complete && <span className={styles.effort}>{item.effort}</span>}
                </div>
                <div className={styles.itemText}>{item.body}</div>
              </div>
              {!complete && (
                <button className={styles.go} onClick={() => onGo(item.id)}>
                  {item.cta}
                  <ArrowRight size={12} />
                </button>
              )}
            </div>
          );
        })}
      </div>

      {done === ITEMS.length && (
        <div className={styles.finished}>
          That is the whole product: your policy, your procedures, your channel,
          your agent. Restoring the sample world leaves all four in place.
        </div>
      )}
    </div>
  );
}
