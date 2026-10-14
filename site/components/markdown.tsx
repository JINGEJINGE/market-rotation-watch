"use client";
import { marked } from "marked";

export function Markdown({ text }: { text: string }) {
  const html = marked.parse(text, { async: false }) as string;
  return <div className="md" dangerouslySetInnerHTML={{ __html: html }} />;
}
