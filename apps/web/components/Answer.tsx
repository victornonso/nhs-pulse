import { Fragment } from "react";
import { timestamp, publication } from "./format";

function inline(text: string) {
  return text
    .split(
      /(\*\*[^*]+\*\*|`[^`]+`|https:\/\/[^\s)]+|\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:\d{2})|\d{4}-\d{2}-\d{2})/g,
    )
    .map((part, i) => {
      if (part.startsWith("**"))
        return <strong key={i}>{part.slice(2, -2)}</strong>;
      if (part.startsWith("`")) return <code key={i}>{part.slice(1, -1)}</code>;
      if (/^\d{4}-\d{2}-\d{2}T/.test(part))
        return <Fragment key={i}>{timestamp(part)}</Fragment>;
      if (/^\d{4}-\d{2}-\d{2}$/.test(part))
        return <Fragment key={i}>{publication(part)}</Fragment>;
      if (part.startsWith("https://")) {
        try {
          const u = new URL(part);
          if (
            [
              "www.england.nhs.uk",
              "digital.nhs.uk",
              "www.data.gov.uk",
            ].includes(u.hostname)
          )
            return (
              <a href={part} key={i} target="_blank" rel="noreferrer">
                Official source ↗
              </a>
            );
        } catch {}
      }
      return <Fragment key={i}>{part}</Fragment>;
    });
}

export default function Answer({ text }: { text: string }) {
  return (
    <div className="answer-text">
      {text.split(/\n\s*\n/).map((block, i) => {
        const lines = block.trim().split("\n");
        const cells = (line: string) =>
          line
            .trim()
            .replace(/^\||\|$/g, "")
            .split("|")
            .map((cell) => cell.trim());
        if (
          lines.length >= 2 &&
          lines[0].includes("|") &&
          cells(lines[1]).every((cell) => /^:?-{3,}:?$/.test(cell))
        ) {
          const headers = cells(lines[0]);
          const rows = lines.slice(2).map(cells);
          if (rows.every((row) => row.length === headers.length))
            return (
              <div
                className="table-scroll"
                key={i}
                tabIndex={0}
                role="region"
                aria-label="Investigation comparison table"
              >
                <table>
                  <caption className="sr-only">
                    Comparison from published evidence
                  </caption>
                  <thead>
                    <tr>
                      {headers.map((cell, n) => (
                        <th scope="col" key={n}>
                          {inline(cell)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, n) => (
                      <tr key={n}>
                        {row.map((cell, col) =>
                          col === 0 ? (
                            <th scope="row" key={col}>
                              {inline(cell)}
                            </th>
                          ) : (
                            <td key={col}>{inline(cell)}</td>
                          ),
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
        }
        if (/^#{1,4}\s+[^\n]+$/.test(block.trim()))
          return (
            <h4 key={i}>{inline(block.trim().replace(/^#{1,4}\s+/, ""))}</h4>
          );
        if (/^\*\*[^*]+\*\*$/.test(block.trim()))
          return <h4 key={i}>{block.trim().slice(2, -2)}</h4>;
        if (block.split("\n").every((line) => /^\s*[-*] /.test(line)))
          return (
            <ul key={i}>
              {block.split("\n").map((line, n) => (
                <li key={n}>{inline(line.replace(/^\s*[-*] /, ""))}</li>
              ))}
            </ul>
          );
        return <p key={i}>{inline(block)}</p>;
      })}
    </div>
  );
}
