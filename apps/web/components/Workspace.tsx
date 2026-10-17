"use client";
import Link from "next/link";
import Answer from "./Answer";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { useCallback, useEffect, useState, useRef } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowUpRight,
  Building2,
  CalendarDays,
  ChartNoAxesCombined,
  ChevronRight,
  Database,
  Globe2,
  HeartPulse,
  Layers3,
  Menu,
  Moon,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sun,
  X,
} from "lucide-react";
import dynamic from "next/dynamic";
import Chart, { type ChartData, type DataRow } from "./Chart";
import { value, month, quarter, publication, timestamp } from "./format";
const Geography = dynamic(() => import("./Geography"), {
  ssr: false,
  loading: () => <div className="skeleton map-skeleton" />,
});
const nav = [
  ["overview", "National Overview", ChartNoAxesCombined],
  ["emergency", "Emergency Care", HeartPulse],
  ["capacity", "Capacity & Beds", Layers3],
  ["trusts", "Trust Explorer", Building2],
  ["geography", "Geographic Intelligence", Globe2],
  ["forecasting", "Forecasting & Trends", Activity],
  ["analyst", "AI Healthcare Analyst", Search],
  ["operations", "Data Operations", Database],
] as const;
const descriptions: Record<string, string> = {
  overview:
    "England hospital activity, waiting-time outcomes and quarterly capacity, in one connected view.",
  emergency:
    "Understand monthly activity, four-hour outcomes and waits after the decision to admit.",
  capacity:
    "Consultant-led capacity from the quarterly KH03 collection. Each denominator stays with its quarter.",
  trusts:
    "Follow a provider from its reported performance to the original statistical release.",
  geography:
    "Explore regional and ICB variation with official boundaries and explicit organisational assignments.",
  forecasting:
    "Historical observations, measured backtests and forecasts with a defined evaluation basis.",
  analyst:
    "Investigate published NHS statistics through bounded analytical tools and inspectable evidence.",
  operations:
    "Publication discovery, immutable evidence, validation and atomic release publication.",
};
type Source = {
  id: string;
  name: string;
  cadence: string;
  last_checked: string | null;
  last_ingested: string | null;
  status: string;
  collection_status?: string;
  latest_period?: string;
  next_announced?: string;
  licence?: string;
  page_url?: string;
};
type Provenance = {
  release_id: string;
  official_publication: string | null;
  ingested_at: string;
  official_url: string;
  version: number;
};
type Metric = {
  label: string;
  value: number | null;
  unit: string;
  period: string | null;
  detail?: string;
  href?: string;
  provenance: Provenance[];
};
type Conversation = {
  id: string;
  question: string;
  created_at: string;
  status: string;
};
type Dashboard = {
  screen: string;
  period: string;
  quarter: string | null;
  diagnostic_period: string | null;
  metrics: Metric[];
  charts: ChartData[];
  table: DataRow[];
  table_kind: string;
  notes: string[];
  sources: Source[];
  regions: { region: string }[];
  provenance: Record<string, Provenance[]>;
  coverage: Record<string, unknown>;
  generation: number;
  configured?: boolean;
  conversations?: Conversation[];
  catalogue?: { id: string; label: string; unit: string; definition: string }[];
  runs?: DataRow[];
  calendar?: DataRow[];
  releases?: DataRow[];
  quality?: DataRow[];
  events?: DataRow[];
  selected_model?: {
    name: string;
    metrics: Record<string, number>;
    metadata: Record<string, unknown>;
    trained_through: string;
  };
  forecast?: DataRow[];
};
async function get<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  const body = await r.json();
  if (!r.ok)
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : "The data request could not be completed.",
    );
  return body;
}
export default function Workspace({ screen }: { screen: string }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: 1, staleTime: 60_000, refetchOnWindowFocus: false },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <Product screen={screen} />
    </QueryClientProvider>
  );
}

function Product({ screen }: { screen: string }) {
  const router = useRouter(),
    path = usePathname(),
    search = useSearchParams();
  const query = search.toString();
  const client = useQueryClient();
  const [dark, setDark] = useState(false),
    [menu, setMenu] = useState(false),
    [methodology, setMethodology] = useState(false),
    [detail, setDetail] = useState<string | null>(null),
    [adminOpen, setAdminOpen] = useState(false),
    [adminKey, setAdminKey] = useState(""),
    [adminSource, setAdminSource] = useState("ae");
  const update = useCallback(
    (key: string, next: string) => {
      const p = new URLSearchParams(query);
      if (next) p.set(key, next);
      else p.delete(key);
      if (key !== "page") p.delete("page");
      if (key === "icb") p.delete("region");
      if (key === "region") p.delete("icb");
      router.replace(path + "?" + p.toString(), { scroll: false });
    },
    [router, path, query],
  );
  useEffect(() => {
    const saved = localStorage.getItem("nhs-pulse-theme");
    setDark(saved === "dark");
    document.documentElement.dataset.theme = saved || "light";
  }, []);
  function theme() {
    const next = !dark;
    setDark(next);
    document.documentElement.dataset.theme = next ? "dark" : "light";
    localStorage.setItem("nhs-pulse-theme", next ? "dark" : "light");
  }
  useEffect(() => {
    function key(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setDetail(null);
        setMethodology(false);
        setAdminOpen(false);
        setMenu(false);
      }
    }
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);
  const publicationSignal = useQuery<{ generation: number }>({
    queryKey: ["publication-signal"],
    queryFn: () => get("/api/v1/publication-generation"),
    refetchInterval: 60_000,
  });
  const observedGeneration = useRef<number | null>(null);
  useEffect(() => {
    const next = publicationSignal.data?.generation;
    if (next === undefined) return;
    if (
      observedGeneration.current !== null &&
      observedGeneration.current !== next
    ) {
      client.invalidateQueries({ queryKey: ["workspace"] });
      client.invalidateQueries({ queryKey: ["periods"] });
      client.invalidateQueries({ queryKey: ["sources"] });
    }
    observedGeneration.current = next;
  }, [publicationSignal.data?.generation, client]);
  const data = useQuery<Dashboard>({
    queryKey: ["workspace", screen, query],
    queryFn: () => get("/api/v1/workspace/" + screen + "?" + query),
    refetchInterval: screen === "operations" ? 60_000 : 300_000,
  });
  const periods = useQuery<{
    months: { period: string }[];
    quarters: { quarter: string }[];
  }>({ queryKey: ["periods"], queryFn: () => get("/api/v1/metadata/periods") });
  const sourceInfo = useQuery<Source[]>({
    queryKey: ["sources"],
    refetchInterval: screen === "operations" ? 60_000 : false,
    queryFn: () => get("/api/v1/operations/sources"),
    enabled: methodology || screen === "operations",
  });
  const profile = useQuery<{
    organisation: DataRow;
    ae: { trend: DataRow[]; summary: DataRow; provenance: Provenance[] };
    beds: { quarter: string; summary: DataRow };
    relationships: DataRow[];
  }>({
    queryKey: ["profile", detail, query],
    queryFn: () => get("/api/v1/organisations/detail/" + detail + "?" + query),
    enabled: !!detail,
  });
  const discovery = useMutation({
    mutationFn: () =>
      get<{ results: { status: string }[] }>("/api/v1/operations/discover", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Admin-Key": adminKey,
        },
        body: JSON.stringify({ source: adminSource, backfill: 1 }),
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["workspace"] });
      client.invalidateQueries({ queryKey: ["sources"] });
    },
  });
  const current = nav.find((n) => n[0] === screen)!;
  const d = data.data;
  const selectPeriod = useCallback(
    (row: DataRow) => {
      if (row.period) update("period", String(row.period).slice(0, 7));
    },
    [update],
  );
  const selectICB = useCallback(
    (code: string) => update("icb", code),
    [update],
  );
  const selectRegion = useCallback(
    (region: string) => update("region", region),
    [update],
  );
  return (
    <div className="app-shell">
      <aside className={"sidebar " + (menu ? "mobile-open" : "")}>
        <Link href="/overview" className="brand">
          <span className="brand-icon">
            <Activity size={23} />
          </span>
          <span>
            NHS <b>Pulse</b>
          </span>
        </Link>
        <span className="side-label">INTELLIGENCE WORKSPACE</span>
        <nav aria-label="Main navigation">
          {nav.map(([slug, title, Icon]) => (
            <Link
              key={slug}
              href={"/" + slug + (query ? "?" + query : "")}
              aria-current={screen === slug ? "page" : undefined}
              onClick={() => setMenu(false)}
            >
              <Icon size={18} />
              <span>{title}</span>
              {screen === slug && <span className="active-dot" />}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div>
            <span className="status-dot" />
            Published public statistics
          </div>
          <p>England · release-aware analysis</p>
          <a href="https://victorokeke.co.uk">
            Built by Victor Okeke <ArrowUpRight size={13} />
          </a>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <button
            className="icon-button menu-button"
            aria-label="Toggle navigation"
            aria-expanded={menu}
            onClick={() => setMenu(!menu)}
          >
            <Menu size={21} />
          </button>
          <div className="breadcrumb">
            <span>NHS Pulse</span>
            <ChevronRight size={13} />
            <strong>{current[1]}</strong>
          </div>
          <div className="top-actions">
            <span className="publication-chip">
              <span className="status-dot" />
              Published statistics
            </span>
            <button
              className="icon-button"
              aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
              onClick={theme}
            >
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button
              className="icon-button"
              aria-label="Publication and source details"
              onClick={() => setMethodology(true)}
            >
              <CalendarDays size={18} />
            </button>
            <span className="avatar" aria-hidden="true">
              NP
            </span>
          </div>
        </header>
        <main id="workspace" className="content">
          <div className="page-heading">
            <div>
              <span className="eyebrow">
                {String(nav.findIndex((n) => n[0] === screen) + 1).padStart(
                  2,
                  "0",
                )}{" "}
                /{" "}
                {screen === "operations"
                  ? "DATA PLATFORM CONTROL"
                  : "HOSPITAL PERFORMANCE INTELLIGENCE"}
              </span>
              <h1>
                {current[1]}
                <span className="title-dot">.</span>
              </h1>
              <p>{descriptions[screen]}</p>
            </div>
            <div className="heading-actions">
              <button
                className="button"
                onClick={() => data.refetch()}
                disabled={data.isFetching}
                aria-label="Reload published analytical views"
              >
                <RefreshCw
                  size={15}
                  className={data.isFetching ? "spin" : ""}
                />
                <span>Reload views</span>
              </button>
              <a
                className="button"
                href={"/api/v1/export/" + screen + "?" + query}
              >
                <ArrowDownToLine size={15} />
                Export CSV
              </a>
              <button className="button" onClick={() => setMethodology(true)}>
                <ShieldCheck size={15} />
                <span>Methodology</span>
              </button>
            </div>
          </div>
          <div className="independence">
            <ShieldCheck size={15} />
            <span>
              Independent analysis using published NHS England statistics.
            </span>
            <button className="link" onClick={() => setMethodology(true)}>
              Sources & definitions <ArrowUpRight size={12} />
            </button>
          </div>
          <div className="filter-bar">
            <CalendarDays size={16} />
            <label>
              {screen === "capacity" ? "Quarter context" : "Reporting month"}
              <select
                aria-label="Reporting month"
                value={search.get("period") || ""}
                onChange={(e) => update("period", e.target.value)}
              >
                <option value="">Latest published</option>
                {periods.data?.months.map((p) => (
                  <option key={p.period} value={p.period.slice(0, 7)}>
                    {month(p.period)}
                  </option>
                ))}
              </select>
            </label>
            {!["operations", "analyst", "forecasting", "capacity"].includes(
              screen,
            ) && (
              <>
                <span className="filter-divider" />
                <label>
                  Region
                  <select
                    aria-label="NHS region"
                    value={search.get("region") || ""}
                    onChange={(e) => update("region", e.target.value)}
                  >
                    <option value="">All England</option>
                    {d?.regions?.map((r) => (
                      <option key={r.region} value={r.region}>
                        {r.region.replace("NHS ENGLAND ", "")}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Departments
                  <select
                    aria-label="A&E department type"
                    value={search.get("type") || "all"}
                    onChange={(e) => update("type", e.target.value)}
                  >
                    <option value="all">All types</option>
                    <option value="type1">Type 1 · major A&E</option>
                    <option value="type2">Type 2 · single specialty</option>
                    <option value="other">Other departments</option>
                  </select>
                </label>
              </>
            )}
            {screen === "emergency" && (
              <label>
                Appointments
                <select
                  aria-label="Booked appointments"
                  value={search.get("booked") || "include"}
                  onChange={(e) => update("booked", e.target.value)}
                >
                  <option value="include">Include booked</option>
                  <option value="exclude">Exclude booked</option>
                </select>
              </label>
            )}
            {screen === "capacity" && (
              <div className="tabs" aria-label="Bed type">
                {["overnight", "day"].map((t) => (
                  <button
                    key={t}
                    aria-pressed={(search.get("bed_type") || "overnight") === t}
                    onClick={() => update("bed_type", t)}
                  >
                    {t === "overnight" ? "Overnight" : "Day only"}
                  </button>
                ))}
              </div>
            )}
            {screen === "forecasting" && (
              <label>
                Horizon
                <select
                  aria-label="Forecast horizon"
                  value={search.get("horizon") || "3"}
                  onChange={(e) => update("horizon", e.target.value)}
                >
                  <option value="3">3 months</option>
                  <option value="6">6 months</option>
                  <option value="12">12 months · where supported</option>
                </select>
              </label>
            )}
            <div className="filter-status">
              <span
                className={"chip " + (screen === "capacity" ? "amber" : "teal")}
              >
                {screen === "capacity"
                  ? "Quarterly publication"
                  : "Official releases"}
              </span>
              {d && (
                <span>
                  {screen === "capacity" ? quarter(d.quarter) : month(d.period)}
                </span>
              )}
            </div>
          </div>
          {data.isError ? (
            <section className="error" role="alert">
              <h2>The analytical view could not be loaded.</h2>
              <p>{data.error.message}</p>
              <button className="button primary" onClick={() => data.refetch()}>
                Try again
              </button>
            </section>
          ) : data.isPending ? (
            <div role="status" aria-label="Loading published statistics">
              <div className="metric-ribbon">
                {[0, 1, 2, 3].map((i) => (
                  <div key={i} className="skeleton metric-skeleton" />
                ))}
              </div>
              <div className="charts">
                <div className="skeleton chart-skeleton" />
                <div className="skeleton chart-skeleton" />
              </div>
            </div>
          ) : (
            d && (
              <>
                {screen === "capacity" && (
                  <div className="notice amber">
                    <CalendarDays size={18} />
                    <p>
                      <strong>
                        {quarter(d.quarter)} · KH03 quarterly return.
                      </strong>{" "}
                      Occupancy uses bed-days within this quarter. These figures
                      do not describe beds available today.
                    </p>
                  </div>
                )}
                {!!d.metrics.length && (
                  <div className="metric-ribbon">
                    {d.metrics.map((m) => (
                      <div className="metric" key={m.label}>
                        <div className="metric-label">
                          {m.href ? (
                            <Link href={m.href + (query ? "?" + query : "")}>
                              {m.label}
                              <ArrowUpRight size={13} />
                            </Link>
                          ) : (
                            m.label
                          )}
                        </div>
                        <strong>{value(m.value, m.unit)}</strong>
                        <div className="metric-meta">
                          <span>{m.unit !== "%" ? m.unit : ""}</span>
                          <span>
                            {screen === "capacity" || m.label.includes("KH03")
                              ? quarter(m.period)
                              : month(m.period)}
                          </span>
                        </div>
                        {m.detail && <p>{m.detail}</p>}
                      </div>
                    ))}
                  </div>
                )}
                {screen === "analyst" ? (
                  <Analyst data={d} />
                ) : (
                  <>
                    {screen === "geography" && (
                      <Geography
                        query={query}
                        onRegion={selectRegion}
                        onICB={selectICB}
                      />
                    )}
                    <div className="charts">
                      {d.charts.map((c, i) => (
                        <div
                          className={
                            i === 0 && screen === "overview"
                              ? "dominant-chart"
                              : ""
                          }
                          key={c.title}
                        >
                          <Chart
                            chart={c}
                            onSelect={
                              c.x === "period" ? selectPeriod : undefined
                            }
                          />
                        </div>
                      ))}
                    </div>
                    {screen === "forecasting" && (
                      <section className="panel">
                        <div className="panel-heading">
                          <div>
                            <h2>Evaluation before extrapolation</h2>
                            <p>
                              Seasonal benchmark, challenger and
                              horizon-specific error evidence
                            </p>
                          </div>
                        </div>
                        {d.selected_model ? (
                          <div className="model-details">
                            <div>
                              <span className="eyebrow">SELECTED MODEL</span>
                              <h3>{d.selected_model.name}</h3>
                              <p>
                                Trained through{" "}
                                {month(d.selected_model.trained_through)}
                              </p>
                            </div>
                            <dl>
                              {Object.entries(d.selected_model.metrics).map(
                                ([k, v]) => (
                                  <div key={k}>
                                    <dt>{k.replaceAll("_", " ")}</dt>
                                    <dd>
                                      {value(
                                        v,
                                        k.toLowerCase().includes("wape")
                                          ? "%"
                                          : "",
                                      )}
                                    </dd>
                                  </div>
                                ),
                              )}
                            </dl>
                            <Table rows={Object.entries(d.selected_model.metadata.candidates || {}).map(([candidate, scores]) => ({candidate,...(scores as Record<string, unknown>)}))} columns={['candidate','MAE','WAPE']} />
                            <p>
                              {String(
                                d.selected_model.metadata.methodology ||
                                  "Rolling-origin evaluation of published monthly aggregate observations.",
                              )}
                            </p>
                          </div>
                        ) : (
                          <div className="empty">
                            Forecasts are withheld until comparable history and
                            evaluation coverage are sufficient.
                          </div>
                        )}
                      </section>
                    )}
                    {screen === "operations" ? (
                      <>
                        <section className="source-grid">
                          {(sourceInfo.data || d.sources).map((s) => (
                            <article className="panel source-card" key={s.id}>
                              <div>
                                <span className="chip">{s.cadence}</span>
                                <span
                                  className={
                                    "chip " +
                                    ([
                                      "failed",
                                      "quarantined",
                                      "delayed",
                                    ].includes(s.status)
                                      ? "amber"
                                      : "teal")
                                  }
                                >
                                  {s.collection_status || s.status}
                                </span>
                              </div>
                              <h2>{s.name}</h2>
                              <dl>
                                <div>
                                  <dt>Reporting period</dt>
                                  <dd>
                                    {s.cadence === "quarterly"
                                      ? quarter(s.latest_period)
                                      : month(s.latest_period)}
                                  </dd>
                                </div>
                                <div>
                                  <dt>Last checked</dt>
                                  <dd>{timestamp(s.last_checked)}</dd>
                                </div>
                                <div>
                                  <dt>Last successful ingestion</dt>
                                  <dd>{timestamp(s.last_ingested)}</dd>
                                </div>
                                <div>
                                  <dt>Next announced release</dt>
                                  <dd>
                                    {s.next_announced
                                      ? timestamp(s.next_announced)
                                      : "Not announced"}
                                  </dd>
                                </div>
                              </dl>
                            </article>
                          ))}
                        </section>
                        <section className="panel">
                          <div className="panel-heading">
                            <div>
                              <h2>Release calendar</h2>
                              <p>
                                Dates from the official publication calendar, in
                                London time
                              </p>
                            </div>
                            <button
                              className="button"
                              onClick={() => setAdminOpen(true)}
                            >
                              <RefreshCw size={15} />
                              Check for new releases
                            </button>
                          </div>
                          <Table
                            rows={d.calendar || []}
                            columns={[
                              "name",
                              "expected_at",
                              "reporting_period",
                            ]}
                            timeFields={["expected_at"]}
                          />
                        </section>
                        <section className="panel">
                          <div className="panel-heading">
                            <div>
                              <h2>Ingestion history</h2>
                              <p>
                                A successful check is separate from a new
                                publication
                              </p>
                            </div>
                          </div>
                          <Table
                            rows={d.runs || []}
                            columns={[
                              "source_id",
                              "status",
                              "started_at",
                              "finished_at",
                              "row_count",
                              "message",
                            ]}
                            timeFields={["started_at", "finished_at"]}
                          />
                        </section>
                        <section className="panel">
                          <div className="panel-heading">
                            <div>
                              <h2>Version and checksum evidence</h2>
                              <p>
                                Immutable raw content, official source and
                                validation lineage
                              </p>
                            </div>
                          </div>
                          <Table
                            rows={d.releases || []}
                            columns={[
                              "source_id",
                              "reporting_period",
                              "published_at",
                              "version",
                              "status",
                              "content_sha256",
                              "row_count",
                            ]}
                            timeFields={["published_at"]}
                          />
                        </section>
                        <section className="panel">
                          <div className="panel-heading">
                            <div>
                              <h2>Validation results</h2>
                              <p>
                                Critical failures preserve the previous
                                published release
                              </p>
                            </div>
                          </div>
                          <Table
                            rows={d.quality || []}
                            columns={[
                              "check_name",
                              "passed",
                              "severity",
                              "checked_at",
                            ]}
                            timeFields={["checked_at"]}
                          />
                        </section>
                        <section className="panel">
                          <div className="panel-heading">
                            <div>
                              <h2>Processing timeline</h2>
                              <p>
                                Download, validation, reconciliation and
                                publication events
                              </p>
                            </div>
                          </div>
                          <Table
                            rows={d.events || []}
                            columns={["state", "at", "run_id", "detail"]}
                            timeFields={["at"]}
                          />
                        </section>
                      </>
                    ) : (
                      d.table.length > 0 && (
                        <ProviderTable
                          data={d}
                          query={query}
                          onDetail={setDetail}
                          update={update}
                          search={search}
                        />
                      )
                    )}
                  </>
                )}
                <section className="release-strip">
                  <span className="eyebrow">BEHIND THESE NUMBERS</span>
                  {Object.entries(d.provenance).map(([source, rows]) => (
                    <div key={source}>
                      <strong>
                        {source === "ae"
                          ? "A&E"
                          : source === "beds"
                            ? "KH03 beds"
                            : "Diagnostics"}
                      </strong>
                      {rows.length ? (
                        rows.map((r) => (
                          <span key={r.release_id}>
                            Published {publication(r.official_publication)}
                            <br />
                            Ingested {timestamp(r.ingested_at)} · version{" "}
                            {r.version}
                            <br />
                            <a
                              href={r.official_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Official source <ArrowUpRight size={12} />
                            </a>
                          </span>
                        ))
                      ) : (
                        <span>No release for this selection</span>
                      )}
                    </div>
                  ))}
                </section>
                <p className="coverage-note">
                  Coverage: {String(d.coverage.ae_organisations)} A&E reporting
                  rows; {String(d.coverage.ae_missing_rows)} with missing
                  attendance or waiting-time values. Diagnostics uses the{" "}
                  {String(d.coverage.diagnostic_grain)} grain.
                </p>
              </>
            )
          )}
          <footer>
            <span>NHS Pulse · Independent published-data analysis</span>
            <span>
              Not affiliated with or endorsed by the NHS. No clinical advice or
              patient-level information.
            </span>
          </footer>
        </main>
      </div>
      {methodology && (
        <Drawer
          title="Sources & methodology"
          close={() => setMethodology(false)}
        >
          <p>
            Observation period, official publication date, last check and
            successful ingestion describe different events. A page visit reloads
            analytical views; it does not run source collection.
          </p>
          {d?.notes.map((note) => (
            <p key={note}>{note}</p>
          ))}
          {sourceInfo.data?.map((s) => (
            <section key={s.id} className="drawer-section">
              <h3>{s.name}</h3>
              <p>
                {s.cadence} publication policy · {s.status}
              </p>
              <p>
                Next announced release:{" "}
                {s.next_announced
                  ? timestamp(s.next_announced)
                  : "Not announced"}
              </p>
              <a href={s.page_url} className="link">
                Official publication page ↗
              </a>
            </section>
          ))}
          <p>
            Definitions and numerical evidence are also available through the{" "}
            <a href="/api/v1/metadata/metrics">metric catalogue</a>. Percentages
            are calculated with their matching denominator, not averaged across
            providers.
          </p>
        </Drawer>
      )}
      {detail && (
        <Drawer title="Trust profile" close={() => setDetail(null)}>
          {profile.isPending ? (
            <div className="skeleton chart-skeleton" />
          ) : profile.isError ? (
            <p role="alert">{profile.error.message}</p>
          ) : (
            profile.data && (
              <>
                <span className="eyebrow">ODS / {detail}</span>
                <h2>{String(profile.data.organisation.name)}</h2>
                <Chart
                  chart={{
                    title: "Published A&E history",
                    rows: profile.data.ae.trend,
                    x: "period",
                    y: "attendances",
                    second: "four_hour_pct",
                    kind: "combo",
                    unit: "attendances",
                    note: "Reporting-month observations; changes in organisational scope require care",
                  }}
                />
                <h3>Related capacity</h3>
                <p>
                  {quarter(profile.data.beds.quarter)} ·{" "}
                  {value(profile.data.beds.summary.occupancy, "%")} occupancy
                </p>
                <p>
                  Source-reported organisation identities and period-specific
                  definitions remain attached to the records.
                </p>
                {profile.data.ae.provenance.map((r) => (
                  <a
                    className="button"
                    key={r.release_id}
                    href={r.official_url}
                  >
                    Original NHS release <ArrowUpRight size={14} />
                  </a>
                ))}
              </>
            )
          )}
        </Drawer>
      )}
      {adminOpen && (
        <Drawer
          title="Authorised release discovery"
          close={() => {
            setAdminOpen(false);
            setAdminKey("");
          }}
        >
          <p>
            Discovery checks the official publication and only publishes a new
            or revised file after validation. It never manufactures a refresh.
          </p>
          <label>
            Source
            <select
              value={adminSource}
              onChange={(e) => setAdminSource(e.target.value)}
            >
              {[
                ["ae", "A&E monthly"],
                ["beds_overnight", "KH03 overnight"],
                ["beds_day", "KH03 day only"],
                ["diagnostics", "Diagnostics monthly"],
              ].map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label>
            Administrator key
            <input
              type="password"
              autoComplete="off"
              value={adminKey}
              onChange={(e) => setAdminKey(e.target.value)}
            />
          </label>
          <button
            className="button primary"
            disabled={!adminKey || discovery.isPending}
            onClick={() => discovery.mutate()}
          >
            {discovery.isPending
              ? "Checking publication…"
              : "Check official publication"}
          </button>
          {discovery.isError && <p role="alert">{discovery.error.message}</p>}
          {discovery.isSuccess && (
            <p role="status">
              Discovery completed:{" "}
              {discovery.data.results.map((r) => r.status).join(", ") ||
                "No new release"}
              .
            </p>
          )}
        </Drawer>
      )}
    </div>
  );
}

function Drawer({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: React.ReactNode;
}) {
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const old = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function trap(e: KeyboardEvent) {
      if (e.key !== "Tab" || !panel.current) return;
      const all = Array.from(
        panel.current.querySelectorAll<HTMLElement>(
          'a[href],button:not(:disabled),input,select,textarea,summary,[tabindex="0"]',
        ),
      ).filter((x) => x.getClientRects().length);
      const first = all[0],
        last = all.at(-1);
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
    }
    document.addEventListener("keydown", trap);
    return () => {
      document.body.style.overflow = old;
      document.removeEventListener("keydown", trap);
      previous?.focus();
    };
  }, []);
  return (
    <div className="drawer-backdrop" onClick={close}>
      <section
        ref={panel}
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <h2>{title}</h2>
          <button
            className="icon-button"
            aria-label="Close panel"
            autoFocus
            onClick={close}
          >
            <X size={20} />
          </button>
        </header>
        <div>{children}</div>
      </section>
    </div>
  );
}
function Table({
  rows,
  columns,
  timeFields = [],
}: {
  rows: DataRow[];
  columns: string[];
  timeFields?: string[];
}) {
  return rows.length ? (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {columns.map((k) => (
              <th key={k}>{k.replaceAll("_", " ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {columns.map((k) => (
                <td key={k}>
                  {k === "published_at"
                    ? publication(r[k])
                    : ["period", "reporting_period"].includes(k)
                      ? String(r.source_id || "").startsWith("beds")
                        ? quarter(r[k])
                        : month(r[k])
                      : timeFields.includes(k)
                        ? timestamp(r[k])
                        : r[k] === null || r[k] === undefined
                          ? "—"
                          : typeof r[k] === "boolean"
                            ? r[k]
                              ? "Passed"
                              : "Failed"
                            : typeof r[k] === "number"
                              ? value(r[k])
                              : typeof r[k] === "object"
                                ? JSON.stringify(r[k])
                                : String(r[k])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <div className="empty">No records for this selection.</div>
  );
}

function ProviderTable({
  data,
  query,
  onDetail,
  update,
  search,
}: {
  data: Dashboard;
  query: string;
  onDetail: (code: string) => void;
  update: (key: string, next: string) => void;
  search: ReturnType<typeof useSearchParams>;
}) {
  const [q, setQ] = useState(search.get("q") || "");
  const [sort, setSort] = useState("attendances");
  const [asc, setAsc] = useState(false);
  const [page, setPage] = useState(1);
  const beds = data.table_kind === "beds";
  const valKey = beds ? "occupancy" : "four_hour_pct";
  const volumeKey = beds ? "available_average" : "attendances";
  const filtered = data.table
    .filter((r) =>
      (String(r.name) + " " + String(r.code))
        .toLowerCase()
        .includes(q.toLowerCase()),
    )
    .sort((a, b) => {
      const key = sort === "attendances" ? volumeKey : sort;
      const x = a[key],
        y = b[key];
      return (
        (key === "name"
          ? String(x).localeCompare(String(y))
          : Number(x ?? -Infinity) - Number(y ?? -Infinity)) * (asc ? 1 : -1)
      );
    });
  const max = Math.max(1, Math.ceil(filtered.length / 15));
  const rows = filtered.slice(
    (Math.min(page, max) - 1) * 15,
    Math.min(page, max) * 15,
  );
  const [selected, setSelected] = useState<string[]>([]);
  const comparison = useQuery<
    { period: string; trend: DataRow[]; summary: DataRow }[]
  >({
    queryKey: ["compare", selected, query],
    queryFn: () =>
      get(
        "/api/v1/organisations/compare?" +
          query +
          "&codes=" +
          selected.join(","),
      ),
    enabled: selected.length > 1,
  });
  function order(k: string) {
    if (sort === k) setAsc(!asc);
    else {
      setSort(k);
      setAsc(false);
    }
  }

  return (
    <section className="panel provider-panel">
      <div className="panel-heading">
        <div>
          <h2>
            {beds ? "Quarterly provider coverage" : "Provider comparison"}
          </h2>
          <p>Volumes and denominators remain visible beside rates</p>
        </div>
        <div className="table-search">
          <Search size={15} />
          <input
            aria-label="Search trusts"
            placeholder="Find a trust or ODS code…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
              update("q", e.target.value);
            }}
          />
        </div>
      </div>
      {selected.length > 0 && (
        <div className="selection-bar">
          {selected.length}/3 selected{" "}
          {selected.map((c) => (
            <button
              key={c}
              onClick={() => setSelected(selected.filter((x) => x !== c))}
            >
              {c} ×
            </button>
          ))}
        </div>
      )}
      {comparison.data && (
        <div className="comparison-results">
          {comparison.data.map((p, i) => (
            <div key={selected[i]}>
              <strong>{selected[i]}</strong>
              <span>
                {value(p.summary.four_hour_pct, "%")} within four hours
              </span>
              <span>
                {value(p.summary.attendances)} attendances · {month(p.period)}
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="table-scroll">
        <table>
          <caption className="sr-only">Published provider performance</caption>
          <thead>
            <tr>
              {data.screen === "trusts" && <th>Select</th>}
              <th>
                <button onClick={() => order("name")}>Trust / provider</button>
              </th>
              <th>ODS code</th>
              <th>
                <button onClick={() => order("attendances")}>
                  {beds ? "Average available beds" : "Attendances"}
                </button>
              </th>
              <th>
                <button onClick={() => order(valKey)}>
                  {beds ? "Occupancy" : "Within four hours"}
                </button>
              </th>
              <th>{beds ? "Occupied bed-days" : "12+ hours after DTA"}</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={String(r.code)}>
                {data.screen === "trusts" && (
                  <td>
                    <input
                      type="checkbox"
                      aria-label={"Compare " + r.name}
                      checked={selected.includes(String(r.code))}
                      disabled={
                        selected.length >= 3 &&
                        !selected.includes(String(r.code))
                      }
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, String(r.code)]
                            : selected.filter((x) => x !== r.code),
                        )
                      }
                    />
                  </td>
                )}
                <th>
                  <button
                    className="link trust-name"
                    onClick={() => onDetail(String(r.code))}
                  >
                    {String(r.name)}
                    <ArrowUpRight size={13} />
                  </button>
                </th>
                <td>
                  <code>{String(r.code)}</code>
                </td>
                <td>{value(r[volumeKey], beds ? "beds" : "")}</td>
                <td>
                  <span className="rate-pill">{value(r[valKey], "%")}</span>
                </td>
                <td>{value(r[beds ? "occupied_bed_days" : "wait_12_plus"])}</td>
                <td>
                  <a className="link" href={String(r.official_url)}>
                    Source ↗
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pagination">
        <span>
          {filtered.length} providers · page {Math.min(page, max)} of {max}
        </span>
        <div>
          <button
            className="button"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </button>
          <button
            className="button"
            disabled={page >= max}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </div>
      </div>
    </section>
  );
}

function Analyst({ data }: { data: Dashboard }) {
  const client = useQueryClient();
  const [question, setQuestion] = useState(""),
    [saved, setSaved] = useState<{
      id?: string;
      answer: string;
      evidence: {
        id: string;
        tool: string;
        result: unknown;
        releases?: Provenance[];
      }[];
    } | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const investigation = useMutation({
    mutationFn: () =>
      get<{
        id: string;
        answer: string;
        evidence: {
          id: string;
          tool: string;
          result: unknown;
          releases?: Provenance[];
        }[];
      }>("/api/v1/analyst/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      }),
    onSuccess: (result) => {
      setSaved(result);
      client.invalidateQueries({ queryKey: ["workspace", "analyst"] });
    },
  });
  const history = useQuery<{
    id: string;
    answer: string;
    evidence: {
      id: string;
      tool: string;
      result: unknown;
      releases?: Provenance[];
    }[];
  }>({
    queryKey: ["investigation", selected],
    queryFn: () => get("/api/v1/analyst/conversations/" + selected),
    enabled: !!selected,
  });
  const answer = history.data || saved;
  return (
    <div className="analyst-workspace">
      <aside className="panel notebook">
        <span className="eyebrow">INVESTIGATIONS</span>
        <h2>Your evidence notebook</h2>
        {data.conversations?.length ? (
          data.conversations.map((c) => (
            <button
              className="saved-question"
              key={c.id}
              onClick={() => {
                setSelected(c.id);
                setQuestion(c.question);
              }}
            >
              <span>{c.question}</span>
              <small>
                {c.status} · {timestamp(c.created_at)}
              </small>
            </button>
          ))
        ) : (
          <p className="quiet">Your saved investigations appear here.</p>
        )}
        <span className="eyebrow">START WITH A QUESTION</span>
        {[
          "Compare the latest A&E attendance and four-hour outcomes with the previous month.",
          "What changed across NHS regions in the latest published month?",
          "Explain the latest KH03 bed quarter and its occupancy denominator.",
        ].map((q) => (
          <button
            className="suggestion"
            key={q}
            onClick={() => {
              setQuestion(q);
              setSelected(null);
            }}
          >
            {q}
            <ArrowUpRight size={14} />
          </button>
        ))}
      </aside>
      <section className="panel investigation">
        <span className="analyst-icon">
          <Activity size={30} />
        </span>
        <span className="eyebrow">ASK. INVESTIGATE. VERIFY.</span>
        <h2>
          A clearer answer starts
          <br />
          with the evidence.
        </h2>
        <p>
          Published statistics. Governed definitions.
          <br />A source release behind every numerical finding.
        </p>
        {!data.configured && (
          <div className="notice amber">
            <ShieldCheck size={18} />
            <div>
              <strong>Provider not connected</strong>
              <p>
                Analytical views and the metric catalogue remain available.
                Investigations require a server-side model connection; no
                simulated answers are shown.
              </p>
            </div>
          </div>
        )}
        {answer && (
          <article className="answer">
            <h3>Investigation result</h3>
            <Answer text={answer.answer} />
          </article>
        )}
        {investigation.isError && (
          <div className="error" role="alert">
            {investigation.error.message}
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setSelected(null);
            investigation.mutate();
          }}
        >
          <label className="sr-only" htmlFor="question">
            Investigation question
          </label>
          <textarea
            id="question"
            placeholder="Ask about published NHS statistics…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={1500}
          />
          <div>
            <span>Read-only tools · Release-linked evidence</span>
            <button
              className="button primary"
              disabled={
                !data.configured ||
                question.trim().length < 5 ||
                investigation.isPending
              }
            >
              {investigation.isPending ? "Investigating…" : "Investigate"}
              <ArrowUpRight size={15} />
            </button>
          </div>
        </form>
      </section>
      <aside className="panel evidence-inspector">
        <h2>Evidence & methodology</h2>
        <p>Inspect the definition before interpreting the number.</p>
        {answer?.evidence.map((e) => (
          <details className="evidence-item" key={e.id}>
            <summary>{e.tool.replaceAll("_", " ")}</summary>
            <code>{e.id}</code>
            <pre>
              {JSON.stringify(
                e.result,
                (_key, v) =>
                  typeof v === "number"
                    ? Math.round(v * 1000) / 1000
                    : typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v)
                      ? timestamp(v)
                      : typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v)
                        ? publication(v)
                        : v,
                2,
              )}
            </pre>
            {e.releases?.map((r) => (
              <a key={r.release_id} href={r.official_url}>
                Official release · {publication(r.official_publication)} ↗
              </a>
            ))}
          </details>
        ))}
        {data.catalogue?.map((m) => (
          <details className="definition" key={m.id}>
            <summary>
              {m.label}
              <span>{m.unit}</span>
            </summary>
            <p>{m.definition}</p>
          </details>
        ))}
        <p className="small-note">
          Aggregate statistics only. No diagnosis, triage or patient-specific
          advice.
        </p>
      </aside>
    </div>
  );
}
