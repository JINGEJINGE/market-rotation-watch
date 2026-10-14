"use client";
import { useEffect, useState } from "react";
import { Markdown } from "@/components/markdown";

export default function Digests() {
  const [files, setFiles] = useState<string[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [text, setText] = useState<string>("");
  useEffect(() => { fetch("/data/digests.json", { cache: "no-store" }).then((r) => r.json()).then((j) => { setFiles(j.files); if (j.files[0]) setSel(j.files[0]); }).catch(() => {}); }, []);
  useEffect(() => { if (sel) fetch(`/data/digests/${sel}`, { cache: "no-store" }).then((r) => r.text()).then(setText); }, [sel]);
  return (
    <>
      <h1>Digest archive</h1>
      <div className="controls"><select value={sel ?? ""} onChange={(e) => setSel(e.target.value)}>{files.map((f) => <option key={f} value={f}>{f.replace(".md", "")}</option>)}</select></div>
      <div className="card"><Markdown text={text} /></div>
    </>
  );
}
