import { codeToHtml } from "shiki";
import styles from "./docs.module.css";
import { CopyButton } from "./CopyButton";

interface Props {
  children: string;
  /** Shiki language id. Falls back to plain text for unknown values. */
  lang?: string;
  /** Label shown in the header bar. Defaults to the language. */
  caption?: string;
}

// Only load grammars we actually use. Anything else renders as plain text
// rather than failing the build.
const SUPPORTED = new Set([
  "bash",
  "sql",
  "python",
  "typescript",
  "javascript",
  "json",
  "yaml",
  "text",
]);

/**
 * Syntax-highlighted code block with a copy button.
 *
 * Highlighting happens at build time in this server component, so the browser
 * receives finished markup and there is no highlight-on-mount flash. The only
 * client JavaScript is the copy button.
 */
export async function CodeBlock({ children, lang = "text", caption }: Props) {
  const code = children.replace(/^\n/, "").replace(/\s+$/, "");
  const language = SUPPORTED.has(lang) ? lang : "text";

  const html = await codeToHtml(code, {
    lang: language,
    theme: "github-dark-default",
  });

  return (
    <figure className={styles.codeFigure}>
      <figcaption className={styles.codeCaption}>
        <span className={styles.codeLang}>{caption ?? lang}</span>
        <CopyButton text={code} />
      </figcaption>
      {/* Shiki output, generated from literal strings in this repository.
          No user input reaches this markup. */}
      <div
        className={styles.shiki}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </figure>
  );
}
