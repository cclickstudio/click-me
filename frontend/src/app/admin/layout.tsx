import AdminSidebar from '@/components/AdminSidebar';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#F9FAFB] dark:bg-[#0F1117] flex transition-colors">
      <AdminSidebar />
      <div className="flex-1 flex flex-col">
        {children}
      </div>
    </div>
  );
}
