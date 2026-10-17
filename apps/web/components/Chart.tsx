"use client";
import { useEffect, useRef } from "react";
import { value, month, quarter } from "./format";
export type DataRow = Record<string, unknown>;
export type ChartData = {
  title: string;
  rows: DataRow[];
  x: string;
  y: string;
  second?: string;
  kind: string;
  unit: string;
  note: string;
};
export default function Chart({
  chart,
  onSelect,
}: {
  chart: ChartData;
  onSelect?: (row: DataRow) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let disposed = false;
    let instance: import("echarts").ECharts | undefined;
    let resize: ResizeObserver | undefined;
    import("echarts").then((e) => {
      if (disposed || !host.current) return;
      instance = e.init(host.current, undefined, { renderer: "canvas" });
      const horizontal = chart.kind === "horizontal";
      const dates = chart.x === "period" || chart.x === "quarter";
      const labels = chart.rows.map((r) =>
        dates
          ? chart.x === "quarter"
            ? quarter(r[chart.x])
            : month(r[chart.x])
          : String(r[chart.x] ?? "Unavailable"),
      );
      const numeric = (key: string) =>
        chart.rows.map((r) =>
          r[key] === null || r[key] === undefined ? null : Number(r[key]),
        );
      const base = {
        name: chart.y.replaceAll("_", " "),
        type: chart.kind === "bar" || horizontal ? "bar" : "line",
        data: numeric(chart.y),
        smooth: false,
        connectNulls: false,
        itemStyle: { color: "#155eef" },
        lineStyle: { width: 2.5 },
        symbolSize: 5,
        barMaxWidth: 30,
        areaStyle: chart.kind === "line" ? { opacity: 0.06 } : undefined,
      };
      const series: unknown[] = [base];
      if (chart.second)
        series.push({
          name: chart.second.replaceAll("_", " "),
          type: "line",
          data: numeric(chart.second),
          yAxisIndex: chart.kind === "combo" ? 1 : 0,
          connectNulls: false,
          itemStyle: { color: "#0c9488" },
          lineStyle: { width: 2, type: "dashed" },
          symbolSize: 4,
        });
      if (chart.kind === "forecast") {
        series.unshift({
          name: "Lower interval",
          type: "line",
          stack: "interval",
          data: numeric("lower_bound"),
          symbol: "none",
          lineStyle: { opacity: 0 },
          areaStyle: { opacity: 0 },
        });
        series.splice(1, 0, {
          name: "Prediction interval",
          type: "line",
          stack: "interval",
          data: chart.rows.map((r) =>
            r.upper_bound === null || r.lower_bound === null
              ? null
              : Number(r.upper_bound) - Number(r.lower_bound),
          ),
          symbol: "none",
          lineStyle: { opacity: 0 },
          areaStyle: { color: "#155eef", opacity: 0.12 },
        });
      }
      const category = {
        type: "category",
        data: labels,
        axisLabel: {
          color: "#526477",
          fontSize: 10,
          hideOverlap: true,
          width: horizontal ? 145 : 80,
          overflow: "truncate",
        },
        axisLine: { lineStyle: { color: "#dce5ee" } },
        axisTick: { show: false },
      };
      const scale = {
        type: "value",
        axisLabel: {
          color: "#526477",
          fontSize: 10,
          formatter: (v: number) =>
            Math.abs(v) >= 1e6
              ? (v / 1e6).toFixed(1) + "m"
              : Math.abs(v) >= 1e3
                ? (v / 1e3).toFixed(0) + "k"
                : v,
        },
        splitLine: { lineStyle: { color: "#e8eef5", type: "dashed" } },
      };
      instance.setOption({
        animation: !matchMedia("(prefers-reduced-motion: reduce)").matches,
        animationDuration: 250,
        grid: {
          left: horizontal ? 165 : 55,
          right: chart.kind === "combo" ? 55 : 22,
          top: chart.second ? 48 : 22,
          bottom: 40,
        },
        legend: {
          show: !!chart.second,
          top: 3,
          textStyle: { color: "#526477", fontSize: 11 },
        },
        tooltip: {
          trigger: "axis",
          confine: true,
          valueFormatter: (v: unknown) => value(v, chart.unit),
        },
        xAxis: horizontal ? scale : category,
        yAxis: horizontal
          ? category
          : chart.kind === "combo"
            ? [
                scale,
                {
                  ...scale,
                  min: 0,
                  max: 100,
                  axisLabel: { ...scale.axisLabel, formatter: "{value}%" },
                },
              ]
            : scale,
        series,
      });
      instance.on("click", (event: { dataIndex: number }) => {
        if (onSelect && event.dataIndex !== undefined)
          onSelect(chart.rows[event.dataIndex]);
      });
      resize = new ResizeObserver(() => instance?.resize());
      resize.observe(host.current);
    });
    return () => {
      disposed = true;
      resize?.disconnect();
      instance?.dispose();
    };
  }, [chart, onSelect]);
  return (
    <section className="panel chart-panel">
      <div className="panel-heading">
        <div>
          <h2>{chart.title}</h2>
          <p>{chart.note}</p>
        </div>
        <span className="unit">{chart.unit}</span>
      </div>
      {chart.rows.length ? (
        <>
          <div
            ref={host}
            className={
              "chart " + (chart.kind === "horizontal" ? "chart-tall" : "")
            }
            role="img"
            aria-label={chart.title}
          />
          <details className="chart-data">
            <summary>View the data</summary>
            <div className="table-scroll">
              <table>
                <caption className="sr-only">{chart.title}</caption>
                <thead>
                  <tr>
                    <th>{chart.x.replaceAll("_", " ")}</th>
                    <th>{chart.y.replaceAll("_", " ")}</th>
                    {chart.second && (
                      <th>{chart.second.replaceAll("_", " ")}</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {chart.rows.map((r, i) => (
                    <tr key={i}>
                      <td>
                        {chart.x === "quarter"
                          ? quarter(r[chart.x])
                          : chart.x === "period"
                            ? month(r[chart.x])
                            : String(r[chart.x] ?? "—")}
                      </td>
                      <td>{value(r[chart.y], chart.unit)}</td>
                      {chart.second && (
                        <td>
                          {value(
                            r[chart.second],
                            chart.kind === "combo" ? "%" : chart.unit,
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      ) : (
        <div className="empty">
          No published observations for this selection.
        </div>
      )}
    </section>
  );
}
