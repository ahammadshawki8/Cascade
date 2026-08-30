"use client";

import { useState } from "react";
import { Check, Plus, Trash2, ArrowLeft } from "lucide-react";
import { EXTENSIONS, Extension } from "./extensions";
import styles from "./ExtensionsPanel.module.css";

/**
 * The auxiliaries, as a shelf rather than as a rail.
 *
 * Every entry here works and none of them is needed by everyone, which is the
 * whole reason this screen exists. Shipping them all on the navigation by
 * default was the honest mistake: eight icons with no explanation reads as a
 * complicated tool rather than as a generous one.
 *
 * Each extension has to make its own case, in the terms someone would actually
 * ask: what is it, when would I open it, how do I use it properly, and what
 * does that look like once. An extension that cannot answer those four
 * questions has no business being in the product, which turned out to be a
 * useful test to have to write down.
 */
export function ExtensionsPanel({
  installed,
  onInstall,
  onRemove,
}: {
  installed: string[];
  onInstall: (id: string) => void;
  onRemove: (id: string) => void;
}) {
  const [open, setOpen] = useState<Extension | null>(null);

  if (open) {
    const isOn = installed.includes(open.id);
    return (
      <div className={styles.panel}>
        <button className={styles.back} onClick={() => setOpen(null)}>
          <ArrowLeft size={14} />
          All extensions
        </button>

        <header className={styles.detailHead}>
          <div>
            <h2 className={styles.detailName}>{open.name}</h2>
            <p className={styles.detailSurface}>{open.surface}</p>
          </div>
          <button
            className={isOn ? styles.remove : styles.install}
            onClick={() => (isOn ? onRemove(open.id) : onInstall(open.id))}
          >
            {isOn ? <Trash2 size={14} /> : <Plus size={14} />}
            {isOn ? "Remove" : "Add to sidebar"}
          </button>
        </header>

        <section className={styles.section}>
          <h3>What it is</h3>
          <p>{open.about}</p>
        </section>

        <section className={styles.section}>
          <h3>When you would use it</h3>
          <p>{open.whenToUse}</p>
        </section>

        <section className={styles.section}>
          <h3>Using it well</h3>
          <ul className={styles.list}>
            {open.howToUse.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>

        <section className={styles.example}>
          <h3>{open.example.title}</h3>
          <p>{open.example.body}</p>
        </section>
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      <header className={styles.head}>
        <h2 className={styles.title}>Extensions</h2>
        <p className={styles.lede}>
          Four destinations are the product: <b>Work</b>, <b>Procedures</b>,{" "}
          <b>Policy</b> and <b>Connections</b>. Everything below is real, works,
          and is not needed by everyone — so it is off until you turn it on.
          Removing one hides the screen; it never deletes anything.
        </p>
      </header>

      <div className={styles.grid}>
        {EXTENSIONS.map((ext) => {
          const isOn = installed.includes(ext.id);
          return (
            <div
              key={ext.id}
              className={`${styles.card} ${isOn ? styles.cardOn : ""}`}
              data-tour={`extension-${ext.id}`}
            >
              <button
                className={styles.cardMain}
                onClick={() => setOpen(ext)}
                aria-label={`Read about ${ext.name}`}
              >
                <span className={styles.cardTop}>
                  <span className={styles.cardName}>{ext.name}</span>
                  {isOn && (
                    <span className={styles.installedTag}>
                      <Check size={11} />
                      Added
                    </span>
                  )}
                </span>
                <span className={styles.cardBlurb}>{ext.blurb}</span>
                <span className={styles.cardSurface}>{ext.surface}</span>
              </button>

              <button
                className={isOn ? styles.remove : styles.install}
                onClick={() => (isOn ? onRemove(ext.id) : onInstall(ext.id))}
              >
                {isOn ? <Trash2 size={13} /> : <Plus size={13} />}
                {isOn ? "Remove" : "Add"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
