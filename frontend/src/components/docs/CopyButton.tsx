"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import styles from "./docs.module.css";

/**
 * Copy-to-clipboard control for code blocks.
 *
 * Client-only because the surrounding CodeBlock is a server component that
 * highlights at build time. Keeping the interactive part this small means the
 * highlighted markup never ships as client JavaScript.
 */
export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Older browsers, or a page served over plain http where the clipboard
      // API is unavailable. Fall back to a hidden textarea.
      const area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      document.body.removeChild(area);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  return (
    <button
      type="button"
      className={styles.copyButton}
      onClick={copy}
      aria-label={copied ? "Copied" : "Copy code"}
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
      <span>{copied ? "Copied" : "Copy"}</span>
    </button>
  );
}
