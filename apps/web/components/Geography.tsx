"use client";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import "maplibre-gl/dist/maplibre-gl.css";
import { value } from "./format";
type Row = Record<string, unknown>;
const normal = (v: unknown) =>
  String(v ?? "")
    .toLowerCase()
    .replace(
      /nhs england|commissioning region|nhs |integrated care board|icb/gi,
      "",
    )
    .trim();
export default function Geography({
  query,
  onRegion,
  onICB,
}: {
  query: string;
  onRegion: (region: string) => void;
  onICB: (code: string) => void;
}) {
  const [kind, setKind] = useState("region");
  const [measure, setMeasure] = useState("four_hour_pct");
  const host = useRef<HTMLDivElement>(null);
  const boundaries = useQuery({
    queryKey: ["boundaries", kind, query],
    queryFn: async () => {
      const r = await fetch(
        "/api/v1/geographies/boundaries?" + query + "&kind=" + kind,
      );
      if (!r.ok) throw new Error("Official boundaries could not be loaded.");
      return r.json();
    },
  });
  const metrics = useQuery<Row[]>({
    queryKey: ["geo-metrics", kind, query],
    queryFn: async () => {
      const r = await fetch(
        "/api/v1/geographies/metrics?" + query + "&kind=" + kind,
      );
      if (!r.ok) throw new Error("Area metrics could not be loaded.");
      return r.json();
    },
  });
  useEffect(() => {
    let disposed = false;
    let map: import("maplibre-gl").Map | undefined;
    if (!boundaries.data || !metrics.data || !host.current) return;
    import("maplibre-gl").then((lib) => {
      lib.setWorkerUrl("/maplibre-worker.mjs");
      if (disposed || !host.current) return;
      const geo = {
        ...boundaries.data,
        features: boundaries.data.features.map((f: { properties: Row }) => {
          const metric = metrics.data?.find(
            (r) =>
              r.code === f.properties.code ||
              normal(r.region || r.name) === normal(f.properties.name),
          );
          return {
            ...f,
            properties: {
              ...f.properties,
              rate:
                metric?.[measure] === undefined || metric?.[measure] === null
                  ? null
                  : Number(metric[measure]),
              filter:
                kind === "region"
                  ? (metric?.region ?? null)
                  : (metric?.code ?? null),
              attendances: metric?.attendances ?? null,
            },
          };
        }),
      };
      map = new lib.Map({
        container: host.current,
        style: {
          version: 8,
          sources: { areas: { type: "geojson", data: geo } },
          layers: [
            {
              id: "paper",
              type: "background",
              paint: { "background-color": "#edf3f8" },
            },
            {
              id: "areas",
              type: "fill",
              source: "areas",
              paint: {
                "fill-color": [
                  "case",
                  ["==", ["get", "rate"], null],
                  "#d8e2ec",
                  [
                    "interpolate",
                    ["linear"],
                    ["get", "rate"],
                    measure === "four_hour_pct" ? 50 : 0,
                    "#dbeafe",
                    measure === "four_hour_pct" ? 70 : 100000,
                    "#5394f7",
                    measure === "four_hour_pct" ? 85 : 250000,
                    "#0c9488",
                    measure === "four_hour_pct" ? 100 : 500000,
                    "#075c57",
                  ],
                ],
                "fill-opacity": 0.9,
              },
            },
            {
              id: "borders",
              type: "line",
              source: "areas",
              paint: { "line-color": "#ffffff", "line-width": 1.4 },
            },
          ],
        },
        center: [-2, 53],
        zoom: 5,
        attributionControl: { compact: false },
      });
      map.addControl(new lib.NavigationControl(), "top-right");
      map.fitBounds(
        [
          [-6.5, 49.8],
          [2.1, 56],
        ],
        { padding: 30, duration: 0 },
      );
      map.on("click", "areas", (e) => {
        const feature = e.features?.[0];
        if (!feature) return;
        const props = feature.properties;
        new lib.Popup()
          .setLngLat(e.lngLat)
          .setText(
            `${props.name}: ${value(props.rate, measure === "four_hour_pct" ? "%" : "")} ${measure === "four_hour_pct" ? "within four hours" : "attendances"}`,
          )
          .addTo(map!);
        if (kind === "region" && props.filter) onRegion(props.filter);
        if (kind === "icb" && props.filter) onICB(props.filter);
      });
      map.on("mouseenter", "areas", () => {
        if (map) map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "areas", () => {
        if (map) map.getCanvas().style.cursor = "";
      });
    });
    return () => {
      disposed = true;
      map?.remove();
    };
  }, [boundaries.data, metrics.data, kind, onRegion, onICB, measure]);
  return (
    <section className="panel geo-panel">
      <div className="panel-heading">
        <div>
          <h2>England, in context</h2>
          <p>Official boundaries · weighted published provider measures</p>
        </div>
        <div className="tabs">
          <button
            aria-pressed={kind === "region"}
            onClick={() => setKind("region")}
          >
            NHS regions
          </button>
          <button aria-pressed={kind === "icb"} onClick={() => setKind("icb")}>
            ICBs
          </button>
        </div>
        <label className="map-measure">
          Measure
          <select
            aria-label="Map measure"
            value={measure}
            onChange={(e) => setMeasure(e.target.value)}
          >
            <option value="four_hour_pct">Within four hours</option>
            <option value="attendances">Attendance volume</option>
          </select>
        </label>
      </div>
      {boundaries.isError || metrics.isError ? (
        <div className="error">
          Geography could not be loaded. The analytical table remains available.
        </div>
      ) : boundaries.isPending ? (
        <div className="skeleton map-skeleton" />
      ) : boundaries.data.features.length ? (
        <div
          ref={host}
          className="map"
          aria-label="Map of official NHS geography boundaries"
        />
      ) : (
        <div className="empty">
          No verified boundary version covers this reporting period.
        </div>
      )}
      <div className="map-legend">
        <span>
          {measure === "four_hour_pct"
            ? "Lower four-hour rate"
            : "Lower attendance volume"}
        </span>
        <i />
        <span>
          {measure === "four_hour_pct" ? "Higher rate" : "Higher volume"}
        </span>
        <span className="missing-key">No comparable data</span>
      </div>
      <p className="panel-note">
        Area assignments describe the published organisational geography, not a
        trust catchment or clinical quality ranking. Contains OS and ONS data ©
        Crown copyright and database right.
      </p>
      <div className="table-scroll">
        <table>
          <caption className="sr-only">
            Accessible geographical comparison
          </caption>
          <thead>
            <tr>
              <th>Area</th>
              <th>Attendances</th>
              <th>Within four hours</th>
            </tr>
          </thead>
          <tbody>
            {metrics.data?.map((r, i) => (
              <tr key={i}>
                <th>
                  {kind === "region" ? (
                    <button
                      className="link"
                      onClick={() => onRegion(String(r.region))}
                    >
                      {String(r.region)}
                    </button>
                  ) : (
                    <button
                      className="link"
                      onClick={() => onICB(String(r.code))}
                    >
                      {String(r.name)}
                    </button>
                  )}
                </th>
                <td>{value(r.attendances)}</td>
                <td>{value(r.four_hour_pct, "%")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
