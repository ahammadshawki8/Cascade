"use client";

import { useEffect, useRef, useState, useId } from "react";
import styles from "./docs.module.css";

interface Props {
  chart: string;
  /** Caption shown under the rendered diagram. */
  caption?: string;
}

/**
 * Mermaid diagram, themed to match the docs.
 *
 * Mermaid is large and only some pages have diagrams, so it is imported
 * dynamically inside the effect rather than at module scope. That keeps it out
 * of the bundle for every page that does not need it.
 *
 * If rendering fails the diagram source is shown instead of an empty box: a
 * reader who can see the source can still follow the structure, and a silent
 * blank would hide the failure from us too.
 */
export function Mermaid({ chart, caption }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const reactId = useId();
  // Mermaid needs a DOM-safe id; React's contains colons.
  const id = `mermaid-${reactId.replace(/[^a-zA-Z0-9]/g, "")}`;

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;

        // Mermaid sizes every node by measuring its label in a detached
        // container, then renders into an SVG that inherits the page font.
        // Two things have to be true or the box comes out smaller than the
        // text and the label is clipped:
        //
        //   1. The font has to be LOADED before measuring. A webfont that
        //      arrives late is measured with fallback metrics.
        //   2. Mermaid has to be given a font stack it can actually resolve.
        //      A `var(--font-…)` reference resolves to nothing in the detached
        //      container, so it measured in sans-serif and drew in IBM Plex.
        //
        // Reading the computed value off our own container gives mermaid the
        // same concrete stack the SVG will inherit.
        if (document.fonts?.ready) await document.fonts.ready;
        if (cancelled) return;

        const fontFamily = container.current
          ? getComputedStyle(container.current).fontFamily
          : "sans-serif";

        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "base",
          fontFamily,
          themeVariables: {
            background: "#0B0E10",
            primaryColor: "#14181B",
            primaryTextColor: "#E8EDF0",
            primaryBorderColor: "#333B42",
            secondaryColor: "#1B2024",
            tertiaryColor: "#14181B",
            lineColor: "#626E77",
            textColor: "#97A3AB",
            mainBkg: "#14181B",
            nodeBorder: "#333B42",
            clusterBkg: "#0F1316",
            clusterBorder: "#262C31",
            edgeLabelBackground: "#0B0E10",
            fontSize: "13px",
          },
          flowchart: {
            curve: "basis",
            padding: 18,
            nodeSpacing: 44,
            rankSpacing: 52,
            useMaxWidth: true,
          },
          sequence: { useMaxWidth: true, actorMargin: 40 },
        });

        const { svg } = await mermaid.render(id, chart.trim());
        if (!cancelled && container.current) {
          container.current.innerHTML = svg;
        }
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [chart, id]);

  if (failed) {
    return (
      <figure className={styles.codeFigure}>
        <figcaption className={styles.codeCaption}>
          <span className={styles.codeLang}>diagram source</span>
        </figcaption>
        <pre className={styles.pre}>
          <code>{chart.trim()}</code>
        </pre>
      </figure>
    );
  }

  return (
    <figure className={styles.diagram}>
      <div ref={container} className={styles.diagramCanvas} />
      {caption && <figcaption className={styles.diagramCaption}>{caption}</figcaption>}
    </figure>
  );
}
