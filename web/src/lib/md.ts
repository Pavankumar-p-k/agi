import { marked, Renderer } from 'marked';
import hljs from 'highlight.js';

class JsxRenderer extends Renderer {
  code(code: string, infostring?: string): string {
    const language = infostring && hljs.getLanguage(infostring) ? infostring : 'plaintext';
    let highlighted: string;
    try {
      highlighted = hljs.highlight(code, { language }).value;
    } catch {
      highlighted = code;
    }
    const escaped = JSON.stringify(code);
    return `<div class="relative group">
      <div class="flex items-center justify-between px-3 py-1.5 text-[10px] rounded-t-lg" style="background:rgba(56,189,248,0.08);color:var(--j-text-dim);border-bottom:0.5px solid var(--j-border)">
        <span>${language}</span>
        <button onclick="navigator.clipboard.writeText(${escaped});this.textContent='Copied!';setTimeout(()=>this.textContent='Copy code',1200)" class="hover:text-[var(--j-sky)] transition-colors">Copy code</button>
      </div>
      <pre class="rounded-b-lg overflow-x-auto p-4 text-[13px] leading-relaxed" style="background:rgba(8,47,73,0.3);border:0.5px solid var(--j-border)"><code class="hljs ${language}">${highlighted}</code></pre>
    </div>`;
  }

  paragraph(text: string): string {
    return `<p style="margin:0.5em 0;line-height:1.7">${text}</p>`;
  }

  link(href: string, _title: string | null, text: string): string {
    return `<a href="${href}" target="_blank" rel="noopener noreferrer" style="color:var(--j-sky);text-decoration:underline">${text}</a>`;
  }

  listitem(text: string): string {
    return `<li style="margin:0.2em 0">${text}</li>`;
  }
}

marked.setOptions({
  breaks: true,
  gfm: true,
});

export function renderMarkdown(text: string): string {
  if (!text) return '';
  const result = marked.parse(text, { renderer: new JsxRenderer() });
  return typeof result === 'string' ? result : '';
}
