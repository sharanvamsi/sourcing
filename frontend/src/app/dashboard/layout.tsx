'use client';

import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { useAuth } from '@/contexts/AuthContext';
import {
  MagnifyingGlassIcon,
  ShoppingCartIcon,
  UserGroupIcon,
  EnvelopeIcon,
  ChartBarIcon,
  Cog6ToothIcon,
  ArrowRightOnRectangleIcon,
} from '@heroicons/react/24/outline';

const navigation = [
  { name: 'Search', href: '/dashboard', icon: MagnifyingGlassIcon },
  { name: 'Basket', href: '/dashboard/basket', icon: ShoppingCartIcon },
  { name: 'Team Leads', href: '/dashboard/team-leads', icon: UserGroupIcon },
];
const pmNavigation = [{ name: 'Outreach', href: '/dashboard/email', icon: EnvelopeIcon }];
const adminNavigation = [{ name: 'Admin', href: '/dashboard/admin', icon: ChartBarIcon }];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading, logout, creditsUsed, basketCount } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !user) router.push('/login');
  }, [user, isLoading, router]);

  if (isLoading) return <div className="min-h-screen flex items-center justify-center"><div className="loading-spinner" /></div>;
  if (!user) return null;

  const allNavigation = [
    ...navigation,
    ...(user.role === 'pm' ? pmNavigation : []),
    ...(user.is_admin ? adminNavigation : []),
  ];
  const isActive = (href: string) => pathname === href || (href !== '/dashboard' && pathname.startsWith(href));
  const initial = user.name?.[0]?.toUpperCase() || 'S';

  return (
    <div className="min-h-screen bg-[#0A0A0A]">
      <aside className="sidebar hidden md:flex fixed inset-y-0 left-0 z-50 w-60 flex-col">
        <Link href="/dashboard" className="flex items-center gap-2 px-6 h-[73px] border-b border-[#1F1F1F]">
          <span className="flex h-7 w-7 items-center justify-center rounded bg-[#3B82F6] text-sm font-semibold text-white">S</span>
          <span className="text-sm font-semibold text-[#F5F5F5]">Sourcing</span>
        </Link>

        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {allNavigation.map((item) => (
            <Link key={item.href} href={item.href} className={`sidebar-link ${isActive(item.href) ? 'active' : ''}`}>
              <item.icon className="h-4 w-4" />
              <span>{item.name}</span>
              {item.name === 'Basket' && basketCount > 0 && <span className="ml-auto rounded-full bg-[#1F1F1F] px-2 py-0.5 text-[10px] text-[#A3A3A3]">{basketCount}</span>}
            </Link>
          ))}
        </nav>

        <div className="px-3 pb-3 space-y-1">
          <Link href="/dashboard/settings" className={`sidebar-link ${isActive('/dashboard/settings') ? 'active' : ''}`}>
            <Cog6ToothIcon className="h-4 w-4" /><span>Settings</span>
          </Link>
          <button onClick={logout} className="sidebar-link w-full text-left">
            <ArrowRightOnRectangleIcon className="h-4 w-4" /><span>Log out</span>
          </button>
        </div>

        <div className="flex items-center gap-3 border-t border-[#1F1F1F] p-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#3B82F6] text-sm font-medium text-white">{initial}</div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-[#F5F5F5]">{user.name}</div>
            <div className="truncate text-xs text-[#A3A3A3]">{user.team_name} · {creditsUsed} credits</div>
          </div>
          <div className="h-2 w-2 rounded-full bg-[#10B981]" />
        </div>
      </aside>

      <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center justify-between border-b border-[#1F1F1F] bg-[#0A0A0A] px-4 md:hidden">
        <Link href="/dashboard" className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded bg-[#3B82F6] text-sm font-semibold text-white">S</span>
          <span className="text-sm font-semibold">Sourcing</span>
        </Link>
        <button onClick={logout} aria-label="Log out" className="p-2 text-[#A3A3A3] hover:text-white"><ArrowRightOnRectangleIcon className="h-5 w-5" /></button>
      </header>

      <nav className="fixed inset-x-0 bottom-0 z-50 flex overflow-x-auto border-t border-[#1F1F1F] bg-[#0A0A0A] md:hidden">
        {[...allNavigation, { name: 'Settings', href: '/dashboard/settings', icon: Cog6ToothIcon }].map((item) => (
          <Link key={item.href} href={item.href} className={`flex min-w-[72px] flex-1 flex-col items-center gap-1 px-2 py-3 text-[10px] ${isActive(item.href) ? 'text-[#3B82F6]' : 'text-[#A3A3A3]'}`}>
            <item.icon className="h-5 w-5" /><span>{item.name}</span>
          </Link>
        ))}
      </nav>

      <main className="min-h-screen px-4 pb-24 pt-20 md:ml-60 md:px-8 md:pb-10 md:pt-8">
        <motion.div key={pathname} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .16 }} className="mx-auto w-full max-w-7xl">
          {children}
        </motion.div>
      </main>
    </div>
  );
}
