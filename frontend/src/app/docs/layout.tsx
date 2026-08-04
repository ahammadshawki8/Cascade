import { ReactNode } from "react";
import styles from "../../components/docs/docs.module.css";
import { DocsNav, DocsPager } from "../../components/docs/DocsNav";

export default function DocsLayout({ children }: { children: ReactNode }) {
  return (
    <div className={styles.shell}>
      <DocsNav />
      <main className={styles.main}>
        <article className={styles.article}>
          {children}
          <DocsPager />
        </article>
      </main>
    </div>
  );
}
