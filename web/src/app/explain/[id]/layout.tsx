/* Server layout for the explain page — hosts generateStaticParams so the
   client page below doesn't need to export it (Next.js restriction). */
export function generateStaticParams() {
  return [{ id: '_placeholder' }];
}

export default function ExplainLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
