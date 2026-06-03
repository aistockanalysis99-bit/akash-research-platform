import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Renders a full markdown report with our .report prose styles.
// Nothing is clipped — the container is the page, not a fixed box.
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="report">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children || ""}</ReactMarkdown>
    </div>
  );
}
