"use client";

import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import styles from "./page.module.css";
import {
  ActivityBar,
  ViewId,
  VIEWS,
  ShellMode,
  viewsFor,
} from "../components/ActivityBar";
import { ExtensionsPanel } from "../components/ExtensionsPanel";
import {
  EXTENSIONS,
  loadInstalled,
  saveInstalled,
  installedViews,
} from "../components/extensions";
import { EvidencePanel } from "../components/EvidencePanel";
import { StatusBar } from "../components/StatusBar";
import { CommandPalette, Command } from "../components/CommandPalette";
import { MetricBar } from "../components/MetricBar";
import { RunbookLibrary, Playbook } from "../components/RunbookLibrary";
import { PolicyPanel, Rule, ImpactResult } from "../components/PolicyPanel";
import { OpsCopilot, CopilotAnswer } from "../components/OpsCopilot";
import { RightRail, ApprovalRequest, Insight } from "../components/RightRail";
import { IntelligencePanel } from "../components/IntelligencePanel";
import { IncidentComposer } from "../components/IncidentComposer";
import type { Explanation, RelearnState, StepEvent } from "../components/runTypes";
import { Tutorial, tutorialSeen, resetTutorial } from "../components/Tutorial";
import { Landing, landingSeen, resetLanding } from "../components/Landing";
import { buildMapModel } from "../components/DecisionMap";
import { RunProgress } from "../components/RunProgress";
import { IncidentInbox } from "../components/IncidentInbox";
import { ConnectionsPanel } from "../components/ConnectionsPanel";
import { RuleComposer } from "../components/RuleComposer";
import { ImportProcedure } from "../components/ImportProcedure";
import { MakeItYours, Progress } from "../components/MakeItYours";
import { RightDock, DockTab } from "../components/RightDock";
import { Shortcuts } from "../components/Shortcuts";
import { RunHistory } from "../components/RunHistory";
import { narrateState } from "../components/narrate";
import { GuidedTour } from "../components/GuidedTour";
import { TOUR, TourEvent } from "../components/tourSteps";
import { ArchitecturePanel } from "../components/ArchitecturePanel";

const API_ROOT = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

/** Public reads and the SSE stream go straight to the API. */
const API_BASE = `${API_ROOT}/api`;

/**
 * Privileged writes go through a same-origin server-side proxy, which attaches
 * the admin token out of the browser's reach. Sending it from here would mean
 * shipping the credential in the page source — see api/proxy/[...path]/route.ts.
 */
const PRIVILEGED = "/api/proxy";

/**
 * The API returns the frozen Day-0 Playbook shape (`uses` / `successes` /
 * `failures`, with freshness carried on `deps`). RunbookLibrary was built
 * against the stub shape. Adapt here rather than editing either side: the
 * models are contract-frozen and the component is Track A's.
 */
function adaptPlaybook(raw: any): Playbook {
  const staleByRule = new Map<string, boolean>();
  for (const dep of raw.deps ?? []) {
    staleByRule.set(dep.rule_key, Boolean(dep.is_stale));
  }

  return {
    playbook_id: raw.playbook_id,
    name: raw.name,
    version: raw.version,
    status_cache: raw.status_cache,
    confidence: raw.confidence,
    usage_count: raw.uses ?? 0,
    success_count: raw.successes ?? 0,
    failure_count: raw.failures ?? 0,
    supersedes: raw.supersedes ?? null,
    origin: raw.origin ?? "compiled",
    spec: {
      steps: raw.spec?.steps ?? [],
      preconditions: raw.spec?.preconditions ?? [],
      rule_citations: (raw.spec?.rule_citations ?? []).map((c: any) => ({
        rule_key: c.rule_key,
        version: c.rule_version,
        // Staleness is derived from the provenance join, not from the spec —
        // the spec only records which version it was compiled against.
        is_stale: staleByRule.get(c.rule_key) ?? false,
        justification: c.why ?? "",
      })),
    },
  };
}

const clockTime = () =>
  new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

/** Pick one, watch it run, understand it, or invent your own. */
type WorkTab = "inbox" | "author" | "history";
type SystemTab = "architecture" | "intelligence";

export default function CascadeApp() {
  const [view, setView] = useState<ViewId>("work");
  /**
   * Which surfaces are on screen.
   *
   * Starts `guided`, always, including for a returning visitor: a reviewer who
   * lands on a four-icon rail has no way to discover that two more exist, and
   * the walkthrough is what earns the right to put them away. Work mode is
   * something you choose at the end of it, and it is remembered once chosen.
   */
  const [shellMode, setShellMode] = useState<ShellMode>("guided");
  /**
   * The landing screen, shown before the app on a first visit.
   *
   * Starts true on the server and is lowered after mount if this browser has
   * been here before, because localStorage is unreachable during SSR and
   * flashing the shell before the landing is worse than a brief hold.
   */
  const [landing, setLanding] = useState(true);
  /**
   * Which auxiliary screens this browser has asked for.
   *
   * Empty by default, in both modes. Four destinations are the product and one
   * is the shelf they come from; shipping the rest on the rail was what made
   * the tool read as complicated rather than as generous.
   */
  const [installed, setInstalled] = useState<string[]>([]);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [tutorialOpen, setTutorialOpen] = useState(false);
  /**
   * The walkthrough, or null when nobody is being walked through anything.
   *
   * Whether a step is *waiting* is not stored: it is `locked`, the same flag
   * that stops overlapping work. The system being busy and the tour waiting
   * for the system are the same fact, and keeping two copies of it is how they
   * come to disagree.
   */
  const [tourStep, setTourStep] = useState<number | null>(null);
  /**
   * The walkthrough resets the world first, and that takes seconds against a
   * Cloud cluster. Until it lands there is nothing safe to click: a run
   * started against the old world gets deleted out from under itself
   * mid-flight, and the tour then waits forever for a compile that can never
   * happen. So the opening card holds the viewer until the world is real.
   */
  const [tourPreparing, setTourPreparing] = useState(false);
  // Opens on the inbox: a blank command box asks the viewer to already know
  // the incident ids and their exact format before anything can happen.
  const [workTab, setWorkTab] = useState<WorkTab>("inbox");
  const [systemTab, setSystemTab] = useState<SystemTab>("architecture");
  /** Copilot and approvals are consulted, not visited. */
  const [dockOpen, setDockOpen] = useState(false);
  const [dockTab, setDockTab] = useState<DockTab>("copilot");
  const [composerOpen, setComposerOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [checklistOff, setChecklistOff] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [setup, setSetup] = useState({ myRules: 0, connections: 0, keys: 0 });
  /** True for one second after `g`, waiting for the destination letter. */
  const goArmed = useRef(false);
  /** A one-off line for the island to announce. */
  const [announce, setAnnounce] = useState<string | null>(null);
  /** Whichever run the island is currently describing. */
  const [lastTaskId, setLastTaskId] = useState<string | null>(null);
  /** Shared by the decision map, the narrator line and the cost footer. */
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [activeIncident, setActiveIncident] = useState<string | null>(null);
  const [compiling, setCompiling] = useState(false);
  const [relearningId, setRelearningId] = useState<string | null>(null);
  const [progressDismissed, setProgressDismissed] = useState(false);
  /** Live phase of a re-learn, streamed by the worker. */
  const [relearn, setRelearn] = useState<RelearnState | null>(null);
  /** The island is showing a past run rather than the one happening now. */
  const [reviewing, setReviewing] = useState(false);
  /** Bumped when the user asks to see detail; the island opens on it. */
  const [islandOpen, setIslandOpen] = useState(0);


  const [metrics, setMetrics] = useState<any>(null);
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [connected, setConnected] = useState(false);

  const [consoleRunning, setConsoleRunning] = useState(false);
  const [consoleMode, setConsoleMode] = useState<"explore" | "guided" | undefined>();
  const [activePlaybookName, setActivePlaybookName] = useState("");
  const [activePlaybookVersion, setActivePlaybookVersion] = useState(0);
  const [consoleSteps, setConsoleSteps] = useState<StepEvent[]>([]);
  /**
   * One thing at a time.
   *
   * A second run started while the first is streaming shares the console's
   * step list and the single explanation slot, so the two interleave and the
   * decision map shows a mixture of both. Compiling and re-learning are the
   * same: they mutate the runbook the next run would retrieve. Rather than
   * making every one of those paths concurrency-safe, the UI refuses to start
   * overlapping work and says why.
   */
  //
  // A re-learn also counts, whoever started it: the cascade queues one on its
  // own when a rule moves, and it rewrites the very runbook the next run would
  // retrieve.
  const relearnInFlight =
    relearn != null &&
    !["done", "rejected", "deferred", "failed"].includes(relearn.phase);
  const busyLabel = consoleRunning
    ? null
    : compiling
      ? "Compiling the runbook from that run"
      : relearningId || relearnInFlight
        ? "Re-learning a quarantined runbook"
        : null;
  const locked =
    consoleRunning || compiling || Boolean(relearningId) || relearnInFlight;

  /**
   * The island is the only live surface, so anything that lands in it has to
   * displace what was there. Clearing first keeps a past run's steps from
   * appearing underneath a new one's decision.
   */
  const clearIsland = useCallback(() => {
    setExplanation(null);
    setConsoleSteps([]);
    setConsoleMode(undefined);
    setActivePlaybookName("");
    setActivePlaybookVersion(0);
    setProgressDismissed(false);
  }, []);

  /**
   * Moving the walkthrough is an event, not a synchronisation.
   *
   * The step also owns which view you are looking at, so the transition sets
   * both together rather than letting an effect chase the step afterwards.
   */
  const goToStep = useCallback((next: number | null) => {
    setTourStep(next);
    if (next == null) return;
    const step = TOUR[next];
    if (step.view) {
      setView(step.view);
      if (step.view === "work") setWorkTab("inbox");
    }
  }, []);

  const MODE_KEY = "cascade_shell_mode";

  // Restore a previously chosen work mode after mount. localStorage is not
  // available during SSR, and defaulting to guided means a first visit is right.
  useEffect(() => {
    if (window.localStorage.getItem(MODE_KEY) === "work") setShellMode("work");
  }, []);

  useEffect(() => {
    if (landingSeen()) setLanding(false);
    setInstalled(loadInstalled());
  }, []);

  const install = useCallback((id: string) => {
    setInstalled((prev) => {
      if (prev.includes(id)) return prev;
      const next = [...prev, id];
      saveInstalled(next);
      return next;
    });
  }, []);

  const removeExtension = useCallback((id: string) => {
    setInstalled((prev) => {
      const next = prev.filter((x) => x !== id);
      saveInstalled(next);
      // Never leave somebody looking at a screen that is no longer on the rail.
      const gone = EXTENSIONS.find((e) => e.id === id)?.view;
      if (gone) setView((cur) => (cur === gone ? "extensions" : cur));
      return next;
    });
  }, []);

  const installedNav = useMemo(() => installedViews(installed), [installed]);

  const applyMode = useCallback((next: ShellMode) => {
    setShellMode(next);
    try {
      window.localStorage.setItem(MODE_KEY, next);
    } catch {
      /* private browsing */
    }
    // Never leave someone looking at a destination that is no longer in the
    // rail. Switching to work mode while on System would otherwise render a
    // view with no way back to it and no icon to explain where it went.
    // Mode no longer decides which destinations exist — Extensions does — so
    // there is nothing to redirect away from here.
  }, []);

  const cancelTour = useCallback(() => setTourStep(null), []);

  const advanceTour = useCallback(() => {
    setTourStep((i) => {
      if (i == null) return null;
      /**
       * Leaving the extensions step turns them all on.
       *
       * The steps after it visit those destinations, and a spotlight pointing
       * at an icon that is not on the rail is worse than no spotlight. Doing it
       * on advance rather than asking also demonstrates the mechanism it is
       * describing: they appear as you continue, and the card says they can be
       * removed again afterwards.
       */
      if (TOUR[i]?.id === "tour-extensions") {
        queueMicrotask(() => EXTENSIONS.forEach((e) => install(e.id)));
      }
      // Finishing the last step is the one place work mode is offered, because
      // it is the only point at which someone has actually seen what they are
      // agreeing to put away.
      if (i + 1 >= TOUR.length) {
        queueMicrotask(() => {
          applyMode("work");
          goToStep(null);
        });
        return i;
      }
      const next = i + 1;
      queueMicrotask(() => goToStep(next));
      return i;
    });
  }, [goToStep, applyMode, install]);

  /**
   * A step ends when the system finishes its half, never on the click.
   *
   * So the walkthrough cannot get ahead of the product: if the compile has not
   * landed, the card still says it is waiting, because it is.
   */
  const fireTour = useCallback(
    (event: TourEvent) => {
      setTourStep((i) => {
        if (i == null) return i;
        const wanted = TOUR[i]?.advanceOn;
        const accepts = Array.isArray(wanted)
          ? wanted.includes(event)
          : wanted === event;
        if (!accepts) return i;
        const next = i + 1 >= TOUR.length ? null : i + 1;
        queueMicrotask(() => goToStep(next));
        return i;
      });
    },
    [goToStep]
  );

  const [copilotAnswer, setCopilotAnswer] = useState<CopilotAnswer | null>(null);
  const [copilotLoading, setCopilotLoading] = useState(false);

  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [insights, setInsights] = useState<Insight[]>([]);

  const [highlightRule, setHighlightRule] = useState<string | undefined>();
  const [prefillParams, setPrefillParams] = useState<Record<string, any> | undefined>();

  const [toast, setToast] = useState<string | null>(null);
  const [episodes, setEpisodes] = useState<any[]>([]);
  const [episodesFor, setEpisodesFor] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const sseRef = useRef<EventSource | null>(null);
  // Listeners are registered per task id, so they must be removable when the
  // next task starts — otherwise a long demo accumulates stale handlers.
  const taskListenersRef = useRef<Array<[string, EventListener]>>([]);

  // ---------------------------------------------------------------- fetching

  const fetchMetrics = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/metrics`);
      if (res.ok) setMetrics(await res.json());
    } catch {}
  }, []);

  // Read synchronously while polling for a freshly compiled runbook: reading
  // `playbooks` there would close over the value from the render that started
  // the poll and never see the update.
  const playbookCountRef = useRef(0);
  const playbooksRef = useRef<Playbook[]>([]);

  const fetchPlaybooks = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/playbooks`);
      if (res.ok) {
        const data = await res.json();
        const next = (data.playbooks ?? []).map(adaptPlaybook);
        playbookCountRef.current = next.length;
        playbooksRef.current = next;
        setPlaybooks(next);
      }
    } catch {}
  }, []);

  const fetchRules = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/rules`);
      if (!res.ok) return;
      const data = await res.json();
      const next = data.rules ?? [];
      setRules(next);
      // "Did you write one of these yourself" is read from the data, not
      // remembered from a button press, so the checklist cannot claim credit
      // for something that did not happen — or lose it on a page reload.
      setSetup((s) => ({ ...s, myRules: next.filter((r: any) => !r.sample).length }));
    } catch {}
  }, []);

  /** Counts that back the "Make it yours" checklist. */
  const fetchSetup = useCallback(async () => {
    const count = async (path: string, key: string) => {
      try {
        const res = await fetch(`${API_BASE}${path}`);
        if (!res.ok) return 0;
        const data = await res.json();
        return (data[key] ?? []).length;
      } catch {
        return 0;
      }
    };
    const [connections, keys] = await Promise.all([
      count("/connections", "connections"),
      count("/keys", "keys"),
    ]);
    setSetup((s) => ({ ...s, connections, keys }));
  }, []);

  const fetchApprovals = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/approvals`);
      if (!res.ok) return;
      const data = await res.json();
      setApprovals(
        (data.approvals ?? []).map((a: any) => ({
          id: a.approval_id,
          incident_id: a.incident_id ?? a.task_input,
          action: a.action,
          // A gate can fire on blast radius alone, with no runbook to score.
          confidence: a.confidence ?? 0,
          reason: a.reason ?? "",
          time: new Date(a.requested_at ?? Date.now()).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
        }))
      );
    } catch {}
  }, []);

  const fetchInsights = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/insights`);
      if (!res.ok) return;
      const data = await res.json();
      setInsights(
        (data.insights ?? []).map((i: any) => ({
          id: i.insight_id,
          title: String(i.kind).replace(/_/g, " "),
          body: i.summary,
          time: new Date(i.created_at ?? Date.now()).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
          suggested_rule_key: i.related_rule_key ?? undefined,
          suggested_params: i.suggested_params ?? undefined,
        }))
      );
    } catch {}
  }, []);

  const refreshAll = useCallback(() => {
    fetchMetrics();
    fetchPlaybooks();
    fetchRules();
    fetchApprovals();
    fetchInsights();
    fetchSetup();
    setRefreshKey((k) => k + 1);
  }, [
    fetchMetrics,
    fetchPlaybooks,
    fetchRules,
    fetchApprovals,
    fetchInsights,
    fetchSetup,
  ]);

  // ---------------------------------------------------------------------- sse

  useEffect(() => {
    refreshAll();

    /**
     * The server names every SSE event after its topic (`event: rule.changed`),
     * so `onmessage` — which only fires for *unnamed* events — never sees any
     * of them. Every subscription below is an explicit addEventListener.
     */
    const es = new EventSource(`${API_BASE}/events?topics=*`);
    sseRef.current = es;

    es.onopen = () => setConnected(true);
    // `onerror` also fires while EventSource is transparently reconnecting, so
    // treating it as terminal latches the indicator to "disconnected" after any
    // blip. readyState is the honest signal: OPEN(1) means live, CONNECTING(0)
    // means it is retrying, CLOSED(2) means it gave up.
    es.onerror = () => setConnected(es.readyState === EventSource.OPEN);
    const health = setInterval(
      () => setConnected(es.readyState === EventSource.OPEN),
      2000
    );

    es.addEventListener("metrics.tick", () => fetchMetrics());
    es.addEventListener("rule.changed", () => {
      fetchRules();
      fetchPlaybooks();
      setRefreshKey((k) => k + 1);
    });
    es.addEventListener("playbook.changed", (e) => {
      fetchPlaybooks();
      fetchMetrics();
      setRefreshKey((k) => k + 1);
      // The compile is the walkthrough's cue to move on, and polling for it
      // was the wrong instrument: in a deployment the job goes through SQS to
      // a Lambda swept once a minute, which outlasts any poll short enough to
      // feel responsive. The worker already announces it.
      try {
        const action = JSON.parse((e as MessageEvent).data)?.action;
        if (action === "created") fireTour("runbook:compiled");
        if (action === "relearned") fireTour("relearn:done");
      } catch {}
    });

    /**
     * Re-learning is four things behind one button, and it used to be a
     * spinner. The worker now narrates each phase, including the ones that end
     * without a new version — which is a legitimate outcome and used to be
     * indistinguishable from the button not having worked.
     */
    es.addEventListener("playbook.relearn", (e) => {
      try {
        const d = JSON.parse((e as MessageEvent).data);
        setRelearn((prev) => ({
          ...(prev?.playbookId === d.playbook_id ? prev : { playbookId: d.playbook_id }),
          playbookId: d.playbook_id,
          phase: d.phase,
          ...(d.name && d.phase !== "done" ? { name: d.name } : {}),
          ...(d.version != null && d.phase !== "done" ? { version: d.version } : {}),
          ...(d.stale_rules ? { staleRules: d.stale_rules } : {}),
          ...(d.task_id ? { taskId: d.task_id } : {}),
          ...(d.task_text ? { taskText: d.task_text } : {}),
          ...(d.result !== undefined ? { result: d.result } : {}),
          ...(d.phase === "done" ? { newName: d.name, newVersion: d.version } : {}),
          ...(d.reason ? { reason: d.reason } : {}),
        }));
        // Any terminal phase, not just the happy one.
        //
        // A re-learn can legitimately end in `rejected`, `deferred` or
        // `failed`, and the walkthrough's last step waited only for `done`.
        // Those three outcomes are the system working correctly and would have
        // left the tour stranded on its final card, which is the worst possible
        // place to strand someone.
        if (["done", "rejected", "deferred", "failed"].includes(d.phase)) {
          fireTour("relearn:done");
        }
      } catch {}
    });
    es.addEventListener("approval.requested", (e) => {
      try {
        const data = JSON.parse((e as MessageEvent).data);
        setApprovals((prev) => [
          {
            id: data.approval_id ?? data.id,
            incident_id: data.incident_id,
            action: data.action,
            confidence: data.confidence ?? 0,
            reason: data.reason,
            time: clockTime(),
          },
          ...prev,
        ]);
        /**
         * A gated action is the one moment the operator must not miss, so it
         * installs its own surface if that surface is not there.
         *
         * Approvals is an extension because it is empty by default: the
         * autonomy gate is off unless somebody raises the threshold. But the
         * instant it does park an action, an uninstalled panel would mean a
         * task waiting on a human who has no way to see it, which is a worse
         * failure than a tab nobody opens.
         */
        install("approvals");
        setDockTab("approvals");
        setDockOpen(true);
        setToast("An action needs your approval.");
      } catch {}
    });
    es.addEventListener("approval.resolved", () => fetchApprovals());
    es.addEventListener("insight.created", () => fetchInsights());
    es.addEventListener("postmortem.created", () => setRefreshKey((k) => k + 1));

    // First visit only. localStorage is unavailable during SSR, so this has to
    // happen after mount — which also means the shell paints behind the modal
    // rather than the modal being the first thing that renders.
    if (!tutorialSeen()) setTutorialOpen(true);

    return () => {
      clearInterval(health);
      es.close();
      sseRef.current = null;
    };
  }, [
    refreshAll,
    fetchMetrics,
    fetchPlaybooks,
    fetchRules,
    fetchApprovals,
    fetchInsights,
    fireTour,
  ]);

  /**
   * The re-learn's own run is a real task, so its steps arrive on the ordinary
   * per-task topic. Attached separately from a user-submitted run on purpose:
   * its terminal status must not load a decision panel for an incident nobody
   * asked about, but its steps are exactly what makes the re-learn watchable.
   */
  useEffect(() => {
    const es = sseRef.current;
    const taskId = relearn?.taskId;
    if (!es || !taskId) return;

    setConsoleSteps([]);
    const onStep = ((e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type !== "step") return;
        setConsoleSteps((prev) => [
          ...prev,
          {
            id: `${taskId}-${data.step_index ?? prev.length}`,
            tool: data.tool,
            args: data.args ?? {},
            output: data.output,
            duration_ms: data.duration_ms,
            error: Boolean(data.error),
          },
        ]);
      } catch {}
    }) as EventListener;

    es.addEventListener(`task.${taskId}.step`, onStep);
    return () => es.removeEventListener(`task.${taskId}.step`, onStep);
  }, [relearn?.taskId]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(timer);
  }, [toast]);

  /**
   * Keyboard: Ctrl-K, Ctrl-\, `?`, and `g` then a letter.
   *
   * The `g`-then-letter pattern is the one Gmail, GitHub and Linear all use, so
   * it costs nothing to learn and makes the app feel like software people have
   * used before rather than a bespoke console.
   */
  useEffect(() => {
    // A shortcut that fires while someone is typing a rule name is a bug, not
    // a feature. Modified keys are still honoured everywhere.
    const typing = (target: EventTarget | null) => {
      const el = target as HTMLElement | null;
      if (!el) return false;
      const tag = el.tagName;
      return (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        el.isContentEditable
      );
    };

    const GO: Record<string, ViewId> = {
      w: "work",
      p: "procedures",
      r: "policy",
      c: "connections",
      s: "system",
    };

    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey) {
        if (e.key.toLowerCase() === "k") {
          e.preventDefault();
          setPaletteOpen((open) => !open);
        } else if (e.key === "\\") {
          e.preventDefault();
          setDockOpen((open) => !open);
        }
        return;
      }

      if (e.altKey || typing(e.target)) return;

      if (e.key === "?") {
        e.preventDefault();
        setShortcutsOpen(true);
        return;
      }
      if (e.key === "Escape") {
        // Everything dismissible, including the introduction. The shortcut map
        // promises "close whatever is open", and an intro card that ignored it
        // would be the first thing to disprove that.
        setShortcutsOpen(false);
        setComposerOpen(false);
        setImportOpen(false);
        setTutorialOpen(false);
        setPaletteOpen(false);
        return;
      }

      const key = e.key.toLowerCase();
      if (key === "g") {
        goArmed.current = true;
        // A prefix that stays armed forever turns every later keypress into a
        // navigation. One second is long enough to be deliberate.
        window.setTimeout(() => {
          goArmed.current = false;
        }, 1000);
        return;
      }
      if (goArmed.current && GO[key]) {
        goArmed.current = false;
        e.preventDefault();
        setView(GO[key]);
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // ------------------------------------------------------------------- tasks

  const detachTaskListeners = useCallback(() => {
    const es = sseRef.current;
    if (es) {
      for (const [name, handler] of taskListenersRef.current) {
        es.removeEventListener(name, handler);
      }
    }
    taskListenersRef.current = [];
  }, []);

  /**
   * A refusal is the whole point of the project and it is completely silent:
   * a runbook matched, the freshness gate rejected it, and the agent quietly
   * re-planned. On screen that is indistinguishable from having no runbook at
   * all, which reads as the retrieval having failed. So say it out loud, and
   * put the evidence one click away.
   */
  const announceDecision = useCallback(async (taskId: string) => {
    try {
      const res = await fetch(`${API_BASE}/tasks/${taskId}/explain`);
      if (!res.ok) return;
      const data = await res.json();
      setExplanation(data);

      /**
       * A cold run that *remediated* is about to become a runbook, but
       * compilation happens in a worker and lands seconds later. Say so, and
       * stop saying it the moment the runbook actually appears.
       *
       * `result === "remediated"` matters and used to be missing. An escalation
       * is also `status: "succeeded"` — the task ran fine, policy simply said
       * no — but the executor deliberately never compiles one, because policy
       * working is not knowledge gained. So a refusal entered this loop and
       * waited the full two minutes for a runbook that was never coming, and
       * `run:finished` fires *after* the loop, which left the walkthrough step
       * watching the refusal apparently frozen for two minutes.
       *
       * The condition now mirrors the executor's own compile gate exactly:
       * explore, and remediated.
       */
      if (
        data?.mode === "explore" &&
        data?.status === "succeeded" &&
        data?.result === "remediated"
      ) {
        setCompiling(true);
        const before = playbookCountRef.current;
        // Long enough to cover a Lambda sweep, which fires once a minute.
        for (let i = 0; i < 60; i++) {
          await new Promise((r) => setTimeout(r, 2000));
          await fetchPlaybooks();
          if (playbookCountRef.current > before) {
            setAnnounce("A runbook was compiled from that run. The next matching incident can reuse it.");
            fireTour("runbook:compiled");
            // Re-read the verdict now that the compile has landed. The first
            // read happened seconds too early to know what this run became,
            // and the panel would otherwise keep saying nothing was saved.
            try {
              const fresh = await fetch(`${API_BASE}/tasks/${taskId}/explain`);
              if (fresh.ok) setExplanation(await fresh.json());
            } catch {}
            break;
          }
        }
        setCompiling(false);
        // Whether or not anything was compiled. A compile can be rejected by
        // the safety lint or deduped into an existing runbook, and both are
        // correct outcomes that leave a walkthrough step waiting on
        // `runbook:compiled` with nothing coming. Firing after a successful
        // compile too is a no-op: the step has already moved on.
        fireTour("compile:settled");
      }

      const reason = data?.decision?.reason;
      fireTour("run:finished");
      if (reason === "reused") fireTour("run:reused");
      if (reason === "refused_stale" || reason === "refused_precondition") {
        fireTour("run:refused");
      }

      // No tab switch: the evidence is in the island, where the run already is.
      if (reason === "refused_stale") {
        setToast("A matching runbook was refused: policy moved since it was compiled.");
      } else if (reason === "refused_precondition") {
        setToast("A matching runbook was refused: its preconditions do not hold here.");
      }
    } catch {}
  }, [fetchPlaybooks, fireTour]);

  /**
   * Step and status topics are per-task (`task.{id}.step`), so handlers can
   * only attach once the id exists. The connection already subscribes to `*`,
   * so this just starts listening — no reconnect.
   */
  const attachTaskListeners = useCallback(
    (taskId: string) => {
      const es = sseRef.current;
      if (!es) return;

      detachTaskListeners();

      const onStep = ((e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          if (data.type === "interrupted") {
            setAnnounce(
              `This run was interrupted mid-flight: ${data.reason ?? "a rule changed"}.`
            );
            return;
          }
          setConsoleSteps((prev) => [
            ...prev,
            {
              id: `${taskId}-${data.step_index ?? prev.length}`,
              tool: data.tool,
              args: data.args ?? {},
              // The tool's own return value. Without it a step can only say
              // what was asked, never what came back — which is where the
              // policy verdict and the rule versions behind it live.
              output: data.output,
              duration_ms: data.duration_ms,
              error: Boolean(data.error),
            },
          ]);
        } catch {}
      }) as EventListener;

      const onStatus = ((e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);

          if (data.status === "running") {
            // Mode comes from the engine's retrieval + freshness decision.
            // Never infer it from the input text — that would show "guided"
            // even when the freshness gate had refused the playbook.
            setConsoleMode(data.mode);
            setActivePlaybookName(data.playbook_name ?? "");
            setActivePlaybookVersion(data.playbook_version ?? 0);
            return;
          }

          if (data.status === "awaiting_approval") {
            setConsoleRunning(false);
            return;
          }

          if (["succeeded", "failed", "interrupted"].includes(data.status)) {
            setConsoleRunning(false);
            if (data.status === "interrupted") {
              setAnnounce(
                "That run was interrupted: a rule changed while it was still going."
              );
            }
            setLastTaskId(taskId);
            void announceDecision(taskId);
            refreshAll();
          }
        } catch {}
      }) as EventListener;

      es.addEventListener(`task.${taskId}.step`, onStep);
      es.addEventListener(`task.${taskId}.status`, onStatus);
      taskListenersRef.current = [
        [`task.${taskId}.step`, onStep],
        [`task.${taskId}.status`, onStatus],
      ];
    },
    [detachTaskListeners, refreshAll, announceDecision]
  );

  const handleTaskSubmit = useCallback(
    async (input: string): Promise<string | null> => {
      setView("work");
      setWorkTab("inbox");
      // No tab switch: the run itself now lives in the floating island, which
      // is visible from wherever you are. Yanking the view around would move
      // the page out from under someone mid-click.
      clearIsland();
      setRelearn(null);
      setReviewing(false);
      setActiveIncident((input.match(/INC-\d+/i) ?? [])[0]?.toUpperCase() ?? input);
      setConsoleRunning(true);
      // The walkthrough hands over to the floating window here: the next thing
      // worth looking at is not on this page.
      fireTour("run:started");

      try {
        const res = await fetch(`${API_BASE}/tasks`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ input }),
        });
        if (!res.ok) {
          setConsoleRunning(false);
          setToast("Could not submit the task.");
          return null;
        }
        const data = await res.json();
        attachTaskListeners(data.task_id);
        return data.task_id;
      } catch {
        setConsoleRunning(false);
        setToast("Could not reach the API.");
        return null;
      }
    },
    [attachTaskListeners, clearIsland, fireTour]
  );

  /**
   * Open a finished run in the island.
   *
   * A past run and a run that has just finished are the same object, so they
   * get the same panel. Anything else would teach a viewer that there are two
   * kinds of explanation, and leave the weaker one attached to history.
   */
  const openRun = useCallback(
    async (taskId: string) => {
      clearIsland();
      setRelearn(null);
      setReviewing(true);
      setConsoleRunning(false);
      setLastTaskId(taskId);
      setIslandOpen((k) => k + 1);

      try {
        const [explainRes, stepsRes] = await Promise.all([
          fetch(`${API_BASE}/tasks/${taskId}/explain`),
          fetch(`${API_BASE}/tasks/${taskId}/steps`),
        ]);

        if (explainRes.ok) {
          const data: Explanation = await explainRes.json();
          setExplanation(data);
          setConsoleMode(data.mode ?? undefined);
          setActiveIncident(
            data.incident?.incident_id ??
              (data.input.match(/INC-\d+/i) ?? [])[0]?.toUpperCase() ??
              data.input
          );
          if (data.playbook) {
            setActivePlaybookName(data.playbook.name);
            setActivePlaybookVersion(data.playbook.version);
          }
        }

        if (stepsRes.ok) {
          const data = await stepsRes.json();
          setConsoleSteps(
            (data.steps ?? []).map((s: any, i: number) => ({
              id: `${taskId}-${s.step_index ?? i}`,
              tool: s.tool,
              args: s.args ?? {},
              output: s.output,
              duration_ms: s.duration_ms,
              error: Boolean(s.error),
            }))
          );
          if (data.retained === false && (data.recorded_steps ?? 0) > 0) {
            setToast(
              `That run took ${data.recorded_steps} steps, but it finished before step detail was kept.`
            );
          }
        }
      } catch {
        setToast("Could not load that run.");
      }
    },
    [clearIsland]
  );

  // ------------------------------------------------------------------ actions

  const handleResetDemo = async () => {
    try {
      await fetch(`${PRIVILEGED}/admin/reset`, { method: "POST" });
      setToast("Demo world reset to a clean v1 state.");
    } catch {
      setToast("Reset failed — is the API running?");
    }
    detachTaskListeners();
    clearIsland();
    setApprovals([]);
    setInsights([]);
    setCopilotAnswer(null);
    setActiveIncident(null);
    setLastTaskId(null);
    setRelearn(null);
    setReviewing(false);
    refreshAll();
  };

  /**
   * Entering work mode empties the workspace without destroying anything.
   *
   * Two halves, and both are needed. Resetting clears what the walkthrough
   * *did* — the runbooks it compiled, the runs, the episodes — while leaving
   * every rule, procedure, connection and key the user brought. Filtering then
   * hides what the walkthrough *shipped with*: the seeded incidents and rules.
   *
   * Deleting the sample outright would be the more literal reading of "empty"
   * and a worse product. The demo world is how anyone evaluates this, and a
   * switch that destroys it is a switch nobody can safely press. Nothing here
   * is unrecoverable: leaving work mode brings it all back.
   */
  const enterWorkMode = useCallback(async () => {
    applyMode("work");
    setView("work");
    setWorkTab("inbox");
    setDockOpen(false);

    /**
     * Work mode is a clean slate, and that includes the sidebar.
     *
     * The walkthrough turns every extension on so it can visit them, which is
     * right for a tour and wrong for the thing you are left holding afterwards:
     * somebody who has just asked for an empty workspace should not find nine
     * icons in it. They are one click away again on the Extensions screen, and
     * that screen is the point.
     */
    setInstalled([]);
    saveInstalled([]);

    /**
     * And the checklist comes back, because in an empty workspace it is the
     * only thing on screen that says what to do next. Dismissing it during the
     * demo was a decision about the demo.
     */
    setChecklistOff(false);

    await handleResetDemo();
    setToast("Work mode. Empty workspace: the checklist is where to start.");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applyMode]);

  /**
   * The walkthrough describes a world in a known state, so it puts the world
   * in that state first.
   *
   * Without the reset, a viewer who has already fixed INC-1001 would be told
   * "the agent has nothing to reuse" and then watch it reuse something. The
   * tour would be lying on its second sentence.
   */
  const startTour = useCallback(async () => {
    setTutorialOpen(false);
    // The walkthrough visits every destination, including the two work mode
    // puts away. Starting it from work mode would send the spotlight to a
    // screen with no icon in the rail, so the tour always restores the full
    // shell first and offers work mode again at the end.
    applyMode("guided");
    setView("work");
    setWorkTab("inbox");
    setTourPreparing(true);
    goToStep(0);
    try {
      await handleResetDemo();
    } finally {
      setTourPreparing(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [goToStep, applyMode]);

  const handleSimulateImpact = async (
    ruleKey: string,
    params: Record<string, any>
  ): Promise<ImpactResult> => {
    const rule = rules.find((r) => r.rule_key === ruleKey);
    const res = await fetch(`${API_BASE}/rules/${ruleKey}/dry-run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: rule?.body ?? "", params }),
    });
    return await res.json();
  };

  /** T2.2 — what a proposed policy would have done to historical incidents. */
  const handleReplay = async (ruleKey: string, params: Record<string, any>) => {
    const res = await fetch(`${API_BASE}/rules/${ruleKey}/replay`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params }),
    });
    if (!res.ok) throw new Error("replay failed");
    return await res.json();
  };

  const handleCommitChange = async (ruleKey: string, params: Record<string, any>) => {
    const rule = rules.find((r) => r.rule_key === ruleKey);
    if (!rule) return;

    const res = await fetch(`${PRIVILEGED}/rules/${ruleKey}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: rule.body, params }),
    });
    fireTour("policy:committed");

    // The receipt, not a reassurance. "Dependent runbooks are being re-checked"
    // throws away the only number that makes this architecture worth building:
    // the write set stayed fixed while the invalidation did not.
    let receipt = `${ruleKey} updated — re-checking every runbook that depends on it`;
    try {
      const impact = await res.json();
      const n = impact?.impacted_playbooks?.length ?? 0;
      if (impact?.writes) {
        receipt =
          `${ruleKey} v${impact.old_version} to v${impact.new_version} · ` +
          `${impact.writes} writes · ${n} runbook${n === 1 ? "" : "s"} invalidated` +
          (impact.duration_ms != null ? ` · ${impact.duration_ms}ms` : "");
      }
    } catch {
      /* the generic line above is still true */
    }
    setAnnounce(receipt);
    setToast(receipt);
    refreshAll();
    // The worker demotes status_cache and queues relearns just after commit.
    setTimeout(refreshAll, 4000);
  };

  const resolveApproval = async (
    approvalId: string,
    decision: "approved" | "rejected"
  ) => {
    try {
      const res = await fetch(`${PRIVILEGED}/approvals/${approvalId}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      });
      const data = await res.json();
      setToast(data.message ?? `Approval ${decision}.`);
    } catch {
      setToast("Could not reach the approvals API.");
    }
    setApprovals((prev) => prev.filter((a) => a.id !== approvalId));
    setTimeout(refreshAll, 3000);
  };

  /**
   * Re-learning is a whole cold run plus a compile, happening in a worker, and
   * it used to report a toast and then nothing for the next minute. That is the
   * final step of the demo, so silence there reads as the button not having
   * worked. Poll until the successor actually exists and keep the card saying
   * what is happening until it does.
   */
  const handleRelearn = async (playbookId: string) => {
    // The user pressed a button and is owed the answer to "what is it doing",
    // so this one does open the panel. An announcement would be the wrong
    // shape: nothing has happened yet, it is about to take a minute.
    clearIsland();
    setReviewing(false);
    setActiveIncident(null);
    setRelearn({
      playbookId,
      phase: "queued",
      name: playbooksRef.current.find((p) => p.playbook_id === playbookId)?.name,
      version: playbooksRef.current.find((p) => p.playbook_id === playbookId)?.version,
    });
    setIslandOpen((k) => k + 1);

    try {
      const res = await fetch(`${PRIVILEGED}/playbooks/${playbookId}/relearn`, {
        method: "POST",
      });
      const body = await res.json();
      setToast(body.message ?? "Re-learn queued.");
      // "Not queued" covers two opposite outcomes. One of them — the cascade
      // already started this re-learn on its own — is progress, and reporting
      // it as a refusal claimed the feature had failed at the exact moment it
      // was working without being asked.
      if (body.state === "superseded") {
        const succ = playbooksRef.current.find((pb) => pb.supersedes === playbookId);
        setRelearn((prev) => ({
          ...(prev ?? { playbookId }),
          playbookId,
          phase: "done",
          newName: succ?.name,
          newVersion: succ?.version,
        }));
        return;
      }
    } catch {
      setToast("Could not queue the re-learn.");
      setRelearn(null);
      return;
    }

    setRelearningId(playbookId);
    // Done when a successor exists, not when the request returned: the worker
    // has to re-solve the incident before there is anything new to show.
    let successor;
    for (let i = 0; i < 45; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      await fetchPlaybooks();
      successor = playbooksRef.current.find((p) => p.supersedes === playbookId);
      if (successor) {
        setToast(`Re-learned as ${successor.name} v${successor.version}.`);
        // Three independent paths now report this — two events and this poll.
        // The event is faster; the poll cannot be missed, because it reads the
        // successor out of the database rather than waiting to be told about
        // it. A walkthrough that stalls on its last step is worse than one
        // that repeats itself, and firing twice is a no-op.
        fireTour("relearn:done");
        break;
      }
    }
    setRelearningId(null);

    // A re-learn can legitimately produce nothing, and the worker says which
    // of the three reasons applies. The only case left to cover here is the
    // one where no phase ever arrived — a lost event, or a worker that never
    // picked the job up — because silence is the one outcome that reads as the
    // button not having worked.
    if (!successor) {
      setRelearn((prev) =>
        prev && !["done", "rejected", "deferred", "failed"].includes(prev.phase)
          ? {
              ...prev,
              phase: "failed",
              reason:
                "The worker did not report back within 90 seconds. The runbook " +
                "stays quarantined.",
            }
          : prev
      );
    }
    refreshAll();
  };

  const handleViewEpisodes = async (playbookId: string) => {
    try {
      const res = await fetch(`${API_BASE}/playbooks/${playbookId}/episodes`);
      const rows = await res.json();
      setEpisodes(Array.isArray(rows) ? rows : []);
    } catch {
      setEpisodes([]);
    }
    setEpisodesFor(playbookId);
  };

  const handleCopilotAsk = async (question: string) => {
    setDockTab("copilot");
    setDockOpen(true);
    setCopilotLoading(true);
    try {
      const res = await fetch(`${API_BASE}/copilot`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      setCopilotAnswer(await res.json());
    } catch {
      setCopilotAnswer({
        question,
        refused: true,
        message: "Could not reach the Copilot API.",
      });
    } finally {
      setCopilotLoading(false);
    }
  };

  // ---------------------------------------------------------------- commands

  const commands = useMemo<Command[]>(() => {
    // Every destination stays reachable from here, in either mode. Work mode is
    // about what is in front of you, not about taking anything away, and a
    // palette that hid what the rail hides would make it a real removal.
    // Everything stays reachable from here. An uninstalled destination is
    // offered with what it would cost — one click that also adds it to the
    // rail, so nobody lands on a screen with no icon to return to.
    const go: Command[] = VIEWS.map((v) => {
      const onRail = viewsFor(installedNav).some((w) => w.id === v.id);
      const ext = EXTENSIONS.find((e) => e.view === v.id);
      return {
        id: `go:${v.id}`,
        label: onRail ? `Go to ${v.label}` : `Add and open ${v.label}`,
        hint: onRail ? v.hint : `${v.hint} · adds it to the sidebar`,
        group: "Navigate",
        run: () => {
          if (!onRail && ext) install(ext.id);
          setView(v.id);
        },
      };
    });

    const modeCommand: Command[] = [
      {
        id: "landing:show",
        label: "Show the opening screen again",
        hint: "The introduction, and the choice between a walkthrough and work",
        group: "Actions",
        run: () => {
          resetLanding();
          setLanding(true);
        },
      },
      shellMode === "work"
        ? {
            id: "mode:guided",
            label: "Show every screen",
            hint: "Bring back System and Evidence",
            group: "Actions",
            run: () => applyMode("guided"),
          }
        : {
            id: "mode:work",
            label: "Switch to work mode",
            hint: "Keep the four screens you operate, put the rest away",
            group: "Actions",
            run: () => applyMode("work"),
          },
    ];

    const runs: Command[] = [
      ["INC-1001", "bad deploy · tier 2 · in window"],
      ["INC-1002", "bad deploy · tier 2 · reuse candidate"],
      ["INC-1003", "bad deploy · tier 1 · policy blocks"],
      ["INC-1004", "bad deploy · outside rollback window"],
      ["INC-1005", "error spike · tier 2"],
      ["INC-1009", "bad deploy · tier 3"],
    ].map(([id, hint]) => ({
      id: `run:${id}`,
      label: `Run incident ${id}`,
      hint,
      group: "Run",
      run: () => {
        void handleTaskSubmit(`Remediate ${id}`);
      },
    }));

    const asks: Command[] = [
      "Which runbooks are stale?",
      "Compare cold vs guided latency",
      "Show all current rules",
      "Summarize the last 20 audit events",
    ].map((q) => ({
      id: `ask:${q}`,
      label: `Ask: ${q}`,
      group: "Copilot",
      run: () => handleCopilotAsk(q),
    }));

    const actions: Command[] = [
      {
        id: "act:scan",
        label: "Scan for new insights",
        hint: "mine history for policy suggestions",
        group: "Actions",
        run: async () => {
          try {
            const res = await fetch(`${PRIVILEGED}/insights/scan`, { method: "POST" });
            const data = await res.json();
            setToast(`Insight scan complete — ${data.found ?? 0} finding(s).`);
            fetchInsights();
          } catch {
            setToast("Insight scan failed.");
          }
        },
      },
      {
        id: "act:generalize",
        label: "Generalize similar runbooks",
        hint: "merge near-duplicates",
        group: "Actions",
        run: async () => {
          try {
            const res = await fetch(`${PRIVILEGED}/generalize`, { method: "POST" });
            const data = await res.json();
            setToast(
              data.count
                ? `Merged ${data.count} cluster(s) into generalized runbooks.`
                : "No runbooks were similar enough to merge."
            );
            refreshAll();
          } catch {
            setToast("Generalization failed.");
          }
        },
      },
      {
        id: "act:index",
        label: "Verify vector index",
        hint: "EXPLAIN proof of pb_embed_idx",
        group: "Actions",
        run: async () => {
          try {
            const res = await fetch(`${PRIVILEGED}/admin/verify-index`);
            const data = await res.json();
            setToast(
              data.uses_index
                ? "Vector index confirmed: pb_embed_idx is in the query plan."
                : `Index NOT used — ${data.error}`
            );
          } catch {
            setToast("Index check failed.");
          }
        },
      },
      {
        id: "act:smoke",
        label: "Check which LLM provider is serving",
        group: "Actions",
        run: async () => {
          try {
            const res = await fetch(`${PRIVILEGED}/admin/smoke`);
            const data = await res.json();
            setToast(
              `chat: ${data.chat_provider ?? "none"} · embeddings: ${data.embed_provider ?? "none"}`
            );
          } catch {
            setToast("Smoke check failed.");
          }
        },
      },
      {
        id: "act:reset",
        label: "Reset demo world",
        hint: "restore clean v1 state",
        group: "Actions",
        run: handleResetDemo,
      },
      {
        id: "act:tour",
        label: "Start the guided walkthrough",
        hint: "one incident at a time, from cold run to re-learn",
        group: "Actions",
        run: startTour,
      },
      {
        id: "act:intro",
        label: "Replay the introduction",
        hint: "what Cascade is and what to watch for",
        group: "Actions",
        run: () => {
          resetTutorial();
          setTutorialOpen(true);
        },
      },
      {
        id: "act:author",
        label: "Author a new incident",
        hint: "test the agent on data it has never seen",
        group: "Actions",
        run: () => {
          setView("work");
          setWorkTab("author");
        },
      },
      {
        id: "act:newrule",
        label: "Write a new policy rule",
        hint: "a rule of your own that the agent must obey",
        group: "Make it yours",
        run: () => {
          setView("policy");
          setComposerOpen(true);
        },
      },
      {
        id: "act:import",
        label: "Import a runbook you already have",
        hint: "paste one in and ground it in policy",
        group: "Make it yours",
        run: () => {
          setView("procedures");
          setImportOpen(true);
        },
      },
      {
        id: "act:connect",
        label: "Connect Slack, or give an agent a key",
        hint: "outbound and inbound, in one place",
        group: "Make it yours",
        run: () => setView("connections"),
      },
      {
        id: "act:dock",
        label: "Toggle the side panel",
        hint: "Copilot and approvals · Ctrl \\",
        group: "Actions",
        run: () => setDockOpen((open) => !open),
      },
      {
        id: "act:why",
        label: "Explain the last run",
        hint: "which gate decided it, and on what evidence",
        group: "Actions",
        run: () => {
          setView("work");
          setWorkTab("history");
        },
      },
      {
        id: "act:docs",
        label: "Open documentation",
        hint: "concepts, API, operations",
        group: "Actions",
        run: () => {
          window.location.href = "/docs";
        },
      },
    ];

    return [...go, ...runs, ...asks, ...actions, ...modeCommand];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handleTaskSubmit, refreshAll, fetchInsights, startTour, shellMode, applyMode, installedNav, install]);

  // ------------------------------------------------------------------ render

  const counts = metrics?.counts_by_status ?? {};
  const hitRate =
    metrics?.retrieval &&
    metrics.retrieval.hits + metrics.retrieval.precondition_misses > 0
      ? Math.round(
          (metrics.retrieval.hits /
            (metrics.retrieval.hits + metrics.retrieval.precondition_misses)) *
            100
        )
      : undefined;

  const activeView = VIEWS.find((v) => v.id === view)!;

  /**
   * How far through "make it yours" the viewer has got.
   *
   * Every field is derived from live data rather than from a flag set when a
   * button was clicked, so it survives a reload, a demo reset and a different
   * browser — and it can never tick a box for something that was started and
   * abandoned.
   */
  const progress: Progress = {
    wroteRule: setup.myRules > 0,
    importedProcedure: playbooks.some(
      (p) => p.origin === "imported" || p.origin === "authored"
    ),
    connectedApp: setup.connections > 0,
    createdKey: setup.keys > 0,
  };
  const allDone = Object.values(progress).every(Boolean);

  /**
   * Which incidents the inbox may show.
   *
   * During the walkthrough, one — so there is never a wrong thing to click.
   * Twelve cards on screen is eleven ways to take the tour somewhere it did
   * not plan for. `null` means no restriction, which is what leaving the tour
   * restores in a single render.
   */
  const tourReveal =
    tourStep === null ? null : (TOUR[tourStep]?.reveal ?? null);

  /** The final step points at the checklist, so the checklist has to be there. */
  const tourHandover = tourStep !== null && TOUR[tourStep]?.id === "handover";

  /**
   * Get the floating window out of the way when the walkthrough is pointing at
   * something else.
   *
   * Expanded, it is large enough to sit on top of the incident list, and the
   * spotlight cannot help with that: it dims what it does not cover, but the
   * window is still physically in front of the card the viewer is being told
   * to click.
   */
  const tourTargetsIsland = (() => {
    if (tourStep === null) return false;
    const t = TOUR[tourStep]?.target;
    const selectors = Array.isArray(t) ? t : t ? [t] : [];
    return selectors.some((sel) =>
      /island|cost|evidence|map/.test(sel)
    );
  })();

  /**
   * The landing owns the first decision, and nothing renders behind it.
   *
   * An overlay would have been less code and worse: the shell showing through
   * gives away the answer before the question has been read, and a viewer who
   * can see an incident list is already reasoning about incidents rather than
   * about whether they want a tour.
   *
   * The early return sits below every hook, so the data layer still connects
   * while this is up. That is deliberate — by the time someone picks an option
   * the metrics are already warm — and it is why this is a return rather than a
   * branch further out.
   */
  if (landing) {
    return (
      <Landing
        onGuided={() => {
          setLanding(false);
          void startTour();
        }}
        onWork={() => {
          setLanding(false);
          void enterWorkMode();
        }}
      />
    );
  }

  return (
    // `appShell` is a plain global class, not a module one. It carries the
    // cursor rules in globals.css, which have to be scoped to the application
    // and kept off the docs site, where an I-beam over prose is correct.
    <div className={`${styles.shell} appShell`}>
      <ActivityBar
        active={view}
        installed={installedNav}
        installedIds={installed}
        onBrand={() => {
          resetLanding();
          setLanding(true);
        }}
        onSelect={setView}
        badges={{ intelligence: insights.length }}
        dockBadge={approvals.length}
        onCommandPalette={() => setPaletteOpen(true)}
        onOpenDock={(tab) => {
          setDockTab(tab);
          setDockOpen(true);
        }}
      />

      <div className={styles.main}>
        <header className={styles.header}>
          <span className={styles.viewTitle}>{activeView.label}</span>
          <span className={styles.viewHint}>{activeView.hint}</span>
          <span className={styles.headerSpacer} />
          {/* One button, and what it offers depends on where you are.
              In guided mode the useful next step is putting the demo away and
              starting for real; in work mode it is seeing the demo again. The
              walkthrough itself stays reachable from Ctrl-K in both. */}
          {tourStep === null &&
            (shellMode === "work" ? (
              <button
                className={styles.headerAction}
                onClick={() => applyMode("guided")}
                title="Bring back the sample world and every screen"
              >
                Explore the demo
              </button>
            ) : (
              <button
                className={styles.headerAction}
                onClick={() => void enterWorkMode()}
                title="Empty the workspace and start on your own material"
              >
                Switch to work mode
              </button>
            ))}
        </header>

        <div className={styles.metrics} data-tour="metrics">
          <MetricBar data={metrics} />
        </div>

        <div className={styles.workspace}>
          <div className={styles.viewport}>
            <div className={styles.view}>
              {view === "work" && (
                <div className={styles.split}>
                  <div className={styles.pane}>
                    <div className={styles.tabs} role="tablist" data-tour="work-tabs">
                      {(
                        [
                          ["inbox", "Inbox", "open incidents waiting to be fixed"],
                          ["author", "Author", "create an incident the system has never seen"],
                          ["history", "History", "past runs, and why each went the way it did"],
                        ] as [WorkTab, string, string][]
                      ).map(([id, label, hint]) => (
                        <button
                          key={id}
                          role="tab"
                          aria-selected={workTab === id}
                          title={hint}
                          className={`${styles.tab} ${
                            workTab === id ? styles.tabActive : ""
                          }`}
                          onClick={() => setWorkTab(id)}
                        >
                          {label}
                        </button>
                      ))}
                    </div>

                    {workTab === "inbox" && (
                      <div className={styles.tabPanel}>
                        <IncidentInbox
                          apiBase={API_BASE}
                          refreshKey={refreshKey}
                          runningId={consoleRunning ? activeIncident : null}
                          locked={locked}
                          only={tourReveal}
                          onRun={(input) => void handleTaskSubmit(input)}
                          onReset={() => void handleResetDemo()}
                          onlyMine={shellMode === "work"}
                        />
                      </div>
                    )}

                    {workTab === "author" && (
                      <div className={styles.tabPanel}>
                        <IncidentComposer
                          apiBase={API_BASE}
                          onRun={(input) => void handleTaskSubmit(input)}
                        />
                      </div>
                    )}

                    {workTab === "history" && (
                      <div className={styles.tabPanel}>
                        <RunHistory
                          apiBase={API_BASE}
                          refreshKey={refreshKey}
                          selectedId={lastTaskId}
                          locked={locked}
                          onSelect={(id) => void openRun(id)}
                        />
                      </div>
                    )}
                  </div>
                  <div className={`${styles.pane} ${styles.paneDivider}`}>
                    {/* The second act, once the walkthrough has made its point.
                        Hidden during the tour so there is never a second thing
                        competing for the click the tour is asking for — except
                        on the final step, which exists to hand over to it. */}
                    {(tourStep === null || tourHandover) && !checklistOff && !allDone && (
                      <div className={styles.checklist} data-tour="make-it-yours">
                        <MakeItYours
                          progress={progress}
                          onDismiss={() => setChecklistOff(true)}
                          onGo={(id) => {
                            if (id === "wroteRule") {
                              setView("policy");
                              setComposerOpen(true);
                            } else if (id === "importedProcedure") {
                              setView("procedures");
                              setImportOpen(true);
                            } else {
                              setView("connections");
                            }
                          }}
                        />
                      </div>
                    )}
                    <RunbookLibrary
                      playbooks={playbooks}
                      compiling={compiling}
                      relearningId={relearningId}
                      onRelearn={handleRelearn}
                      onViewEpisodes={handleViewEpisodes}
                      onImport={() => setImportOpen(true)}
                    />
                  </div>
                </div>
              )}

              {view === "procedures" && (
                <div className={styles.full}>
                  <div className={styles.paneHead}>
                    <span className={styles.paneHint}>
                      Runbooks the agent learned, and runbooks you brought. Both
                      are governed the same way.
                    </span>
                    <span className={styles.headerSpacer} />
                    <button
                      className={styles.headerAction}
                      onClick={() => setImportOpen(true)}
                      data-tour="import-procedure"
                    >
                      Import a runbook
                    </button>
                  </div>
                  <RunbookLibrary
                    playbooks={playbooks}
                    onRelearn={handleRelearn}
                    onViewEpisodes={handleViewEpisodes}
                    onImport={() => setImportOpen(true)}
                  />
                </div>
              )}

              {view === "policy" && (
                <div className={styles.full}>
                  <div className={styles.paneHead}>
                    <span className={styles.paneHint}>
                      Every rule here gates the agent. Changing one costs four
                      writes, whatever depends on it.
                    </span>
                    <span className={styles.headerSpacer} />
                    <button
                      className={styles.headerAction}
                      onClick={() => setComposerOpen(true)}
                      data-tour="new-rule"
                    >
                      New rule
                    </button>
                  </div>
                  <PolicyPanel
                    rules={rules}
                    onSimulateImpact={handleSimulateImpact}
                    onCommitChange={handleCommitChange}
                    onReplay={handleReplay}
                    highlightRuleKey={highlightRule}
                    prefillParams={prefillParams}
                    hideSample={shellMode === "work"}
                  />
                </div>
              )}

              {view === "connections" && (
                <div className={styles.full}>
                  <ConnectionsPanel
                    apiBase={API_BASE}
                    privileged={PRIVILEGED}
                    refreshKey={refreshKey}
                    onToast={setToast}
                  />
                </div>
              )}

              {view === "system" && (
                <div className={styles.full}>
                  <ArchitecturePanel apiBase={API_BASE} refreshKey={refreshKey} />
                </div>
              )}

              {view === "intelligence" && (
                <div className={styles.full}>
                  <IntelligencePanel apiBase={API_BASE} refreshKey={refreshKey} />
                </div>
              )}

              {view === "extensions" && (
                <div className={styles.full}>
                  <ExtensionsPanel
                    installed={installed}
                    onInstall={install}
                    onRemove={removeExtension}
                  />
                </div>
              )}

              {view === "evidence" && (
                <div className={styles.full}>
                  <EvidencePanel />
                </div>
              )}
            </div>
          </div>

          <RightDock
            open={dockOpen}
            tab={dockTab}
            approvalCount={approvals.length}
            available={
              ["copilot", "approvals"].filter((x) =>
                installed.includes(x)
              ) as DockTab[]
            }
            onTab={setDockTab}
            onClose={() => setDockOpen(false)}
          >
            {dockTab === "copilot" ? (
              <OpsCopilot
                answer={copilotAnswer}
                isLoading={copilotLoading}
                onAsk={handleCopilotAsk}
              />
            ) : (
              <RightRail
                approvals={approvals}
                insights={insights}
                embedded
                onClose={() => setDockOpen(false)}
                onApprove={(id) => void resolveApproval(id, "approved")}
                onReject={(id) => void resolveApproval(id, "rejected")}
                onReviewPolicy={(key, params) => {
                  // Carry the insight's suggested parameters into the Policy
                  // Panel so acting on a recommendation is one click.
                  setHighlightRule(key);
                  setPrefillParams(params);
                  setView("policy");
                }}
              />
            )}
          </RightDock>
        </div>

        <StatusBar
          llm={metrics?.llm}
          llmProvider={metrics?.llm_provider}
          connected={connected}
          running={counts.running ?? 0}
          succeeded={counts.succeeded ?? 0}
          failed={counts.failed ?? 0}
          awaitingApproval={approvals.length}
          hitRate={hitRate}
          onOpenPalette={() => setPaletteOpen(true)}
          onOpenIntelligence={() => {
            setView("system");
            setSystemTab("intelligence");
          }}
        />
      </div>

      <CommandPalette
        open={paletteOpen}
        commands={commands}
        onClose={() => setPaletteOpen(false)}
      />

      {(activeIncident || busyLabel || relearn) && !progressDismissed && (
        <RunProgress
          running={consoleRunning}
          steps={consoleSteps}
          mode={consoleMode}
          explanation={explanation}
          relearn={relearn}
          announce={announce}
          busyLabel={busyLabel}
          compiling={compiling}
          openSignal={islandOpen}
          hostCollapsed={tourStep !== null && !tourTargetsIsland}
          reviewing={reviewing}
          onOpenPolicy={(key) => {
            setHighlightRule(key);
            setView("policy");
          }}
          onDismiss={() => {
            setProgressDismissed(true);
            setRelearn(null);
          }}
          model={buildMapModel({
            incident: activeIncident,
            running: consoleRunning,
            mode: consoleMode,
            playbookName: activePlaybookName,
            playbookVersion: activePlaybookVersion,
            explanation,
          })}
          narration={narrateState({
            running: consoleRunning,
            mode: consoleMode,
            playbookName: activePlaybookName,
            outcome: explanation?.result,
            refusal: explanation?.decision?.reason ?? null,
          })}
        />
      )}

      {tutorialOpen && (
        <Tutorial
          onStartTour={() => void startTour()}
          onClose={() => setTutorialOpen(false)}
        />
      )}

      {composerOpen && (
        <RuleComposer
          apiBase={API_BASE}
          privileged={PRIVILEGED}
          onClose={() => setComposerOpen(false)}
          onCreated={refreshAll}
          onToast={setToast}
        />
      )}

      {importOpen && (
        <ImportProcedure
          apiBase={API_BASE}
          privileged={PRIVILEGED}
          onClose={() => setImportOpen(false)}
          onImported={refreshAll}
          onToast={setToast}
        />
      )}

      {/* Last in the tree so its spotlight sits above the island and the
          command palette — the two things a step may need to point at. */}
      {tourStep !== null && (
        <GuidedTour
          steps={TOUR}
          index={tourStep}
          waiting={locked}
          preparing={tourPreparing}
          onAdvance={advanceTour}
          onCancel={cancelTour}
        />
      )}

      {shortcutsOpen && <Shortcuts onClose={() => setShortcutsOpen(false)} />}

      {toast && <div className={styles.toast}>{toast}</div>}

      {episodesFor && (
        <div className={styles.modalOverlay} onClick={() => setEpisodesFor(null)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <div className={styles.modalTitle}>Episodes for this runbook</div>
            {episodes.length === 0 ? (
              <div className={styles.empty}>
                No runs yet — episodes appear once this runbook executes.
              </div>
            ) : (
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>task</th>
                    <th>outcome</th>
                    <th>mode</th>
                    <th>steps</th>
                    <th>latency</th>
                  </tr>
                </thead>
                <tbody>
                  {episodes.map((ep) => (
                    <tr key={ep.episode_id}>
                      <td>{ep.task_input}</td>
                      <td>{ep.outcome}</td>
                      <td>{ep.mode}</td>
                      <td>{ep.steps}</td>
                      <td>{ep.latency_ms}ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
