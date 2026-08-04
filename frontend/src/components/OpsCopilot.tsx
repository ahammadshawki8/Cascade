"use client";

import { useState } from "react";
import { Send, ChevronDown, ChevronRight } from "lucide-react";
import styles from "./OpsCopilot.module.css";

export interface CopilotAnswer {
  question: string;
  sql?: string;
  columns?: string[];
  rows?: any[][];
  refused?: boolean;
  message?: string;
}

interface OpsCopilotProps {
  answer: CopilotAnswer | null;
  isLoading: boolean;
  onAsk: (question: string) => void;
}

const SUGGESTIONS = [
  "Why did rollback runbooks fail this week?",
  "Summarize the last 20 audit events",
  "Which policies changed most recently?",
];

export function OpsCopilot({ answer, isLoading, onAsk }: OpsCopilotProps) {
  const [input, setInput] = useState("");
  const [sqlOpen, setSqlOpen] = useState(true);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !isLoading) {
      onAsk(input);
      setInput("");
      setSqlOpen(true); // reset to open for new answers
    }
  };

  const handleSuggestionClick = (suggestion: string) => {
    onAsk(suggestion);
    setSqlOpen(true);
  };

  return (
    <div className={styles.copilot}>
      <div className={styles.header}>
        <span className={styles.title}>Ops Copilot</span>
      </div>

      <div className={styles.body}>
        {!answer && !isLoading ? (
          <div className={styles.emptyState}>
            <div className={styles.suggestionsTitle}>Suggested queries</div>
            {SUGGESTIONS.map((s, i) => (
              <button 
                key={i} 
                className={styles.suggestionChip}
                onClick={() => handleSuggestionClick(s)}
              >
                {s}
              </button>
            ))}
          </div>
        ) : null}

        {isLoading ? (
          <div className={styles.answerBox}>
            <span className={styles.refusal}>Analyzing...</span>
          </div>
        ) : answer ? (
          <div className={styles.answerBox}>
            <div className={styles.question}>{answer.question}</div>

            {answer.refused ? (
              <div className={styles.refusal}>{answer.message || "Request refused."}</div>
            ) : (
              <>
                {answer.columns && answer.rows && (
                  <div className={styles.tableWrapper}>
                    <table className={styles.table}>
                      <thead>
                        <tr className={styles.tr}>
                          {answer.columns.map((col, i) => (
                            <th key={i} className={styles.th}>{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {answer.rows.map((row, i) => (
                          <tr key={i} className={styles.tr}>
                            {row.map((cell, j) => (
                              <td key={j} className={styles.td}>{String(cell)}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {answer.sql && (
                  <div className={styles.sqlWrapper}>
                    <div 
                      className={styles.sqlHeader}
                      onClick={() => setSqlOpen(!sqlOpen)}
                    >
                      <span>Generated SQL</span>
                      {sqlOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    </div>
                    {sqlOpen && (
                      <div className={styles.sqlCode}>
                        {answer.sql}
                      </div>
                    )}
                  </div>
                )}

                <div className={styles.disclaimer}>
                  Exploratory — generated SQL shown above; verify before acting.
                </div>
              </>
            )}
          </div>
        ) : null}
      </div>

      <div className={styles.footer}>
        <form className={styles.inputWrapper} onSubmit={handleSubmit}>
          <input
            className={styles.input}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about runbooks, policies, or events..."
            disabled={isLoading}
          />
          <button 
            type="submit" 
            className={styles.submitBtn}
            disabled={!input.trim() || isLoading}
          >
            <Send size={16} />
          </button>
        </form>
      </div>
    </div>
  );
}
