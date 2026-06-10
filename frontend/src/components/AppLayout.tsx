import Navigation from './Navigation';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#F9FAFB] dark:bg-[#0F1117] transition-colors">
      <Navigation />
      <main className="pt-14">{children}</main>
    </div>
  );
}
