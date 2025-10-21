'use client';

export default function ClusterDetailLoading() {
  return (
    <div className="flex flex-col gap-6 animate-pulse">
      <div className="h-4 w-32 rounded bg-slate-800" />
      <header className="flex flex-col gap-3">
        <div className="h-3 w-40 rounded bg-slate-800" />
        <div className="h-8 w-3/4 rounded bg-slate-800" />
        <div className="flex flex-wrap gap-3">
          <div className="h-4 w-32 rounded bg-slate-800" />
          <div className="h-4 w-20 rounded bg-slate-800" />
        </div>
      </header>
      <section className="h-32 rounded-xl border border-slate-800 bg-slate-900/40" />
      <section className="h-32 rounded-xl border border-slate-800 bg-slate-900/40" />
      <section className="grid gap-4 md:grid-cols-2">
        <div className="h-32 rounded-xl border border-slate-800 bg-slate-900/40" />
        <div className="h-32 rounded-xl border border-slate-800 bg-slate-900/40" />
      </section>
      <section className="h-24 rounded-xl border border-slate-800 bg-slate-900/40" />
    </div>
  );
}
