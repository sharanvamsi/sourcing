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

const pmNavigation = [
  { name: 'Email Outreach', href: '/dashboard/email', icon: EnvelopeIcon },
];

const adminNavigation = [
  { name: 'Admin', href: '/dashboard/admin', icon: ChartBarIcon },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading, logout, creditsUsed, basketCount } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
    }
  }, [user, isLoading, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="loading-spinner" />
      </div>
    );
  }

  if (!user) {
    return null;
  }

  const isPM = user.role === 'pm';
  const isAdmin = user.is_admin;

  const allNavigation = [
    ...navigation,
    ...(isPM ? pmNavigation : []),
    ...(isAdmin ? adminNavigation : []),
  ];

  return (
    <div className="min-h-screen flex">
      {/* Gradient background */}
      <div className="gradient-bg">
        <div className="glow-orb glow-orb-1" />
        <div className="glow-orb glow-orb-2" />
      </div>

      {/* Sidebar */}
      <motion.aside
        initial={{ x: -280 }}
        animate={{ x: 0 }}
        transition={{ duration: 0.3 }}
        className="sidebar w-64 fixed h-full flex flex-col z-20"
      >
        {/* Logo */}
        <div className="p-6 border-b border-white/10">
          <h1 className="text-xl font-bold bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
            ABA Sourcing
          </h1>
        </div>

        {/* User info */}
        <div className="p-4 border-b border-white/10">
          <div className="text-sm font-medium">{user.name}</div>
          <div className="text-xs text-gray-400">{user.team_name}</div>
          <div className="flex items-center gap-4 mt-3 text-xs">
            <div>
              <span className="text-gray-400">Credits:</span>{' '}
              <span className="text-white font-medium">{creditsUsed}</span>
            </div>
            <div>
              <span className="text-gray-400">Basket:</span>{' '}
              <span className="text-white font-medium">{basketCount}</span>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-1">
          {allNavigation.map((item) => {
            const isActive = pathname === item.href ||
              (item.href !== '/dashboard' && pathname.startsWith(item.href));
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`sidebar-link ${isActive ? 'active' : ''}`}
              >
                <item.icon className="w-5 h-5" />
                {item.name}
              </Link>
            );
          })}
        </nav>

        {/* Settings & Logout */}
        <div className="p-4 border-t border-white/10 space-y-1">
          <Link href="/dashboard/settings" className="sidebar-link">
            <Cog6ToothIcon className="w-5 h-5" />
            Settings
          </Link>
          <button onClick={logout} className="sidebar-link w-full text-left">
            <ArrowRightOnRectangleIcon className="w-5 h-5" />
            Logout
          </button>
        </div>
      </motion.aside>

      {/* Main content */}
      <main className="flex-1 ml-64 p-8 relative z-10">
        <motion.div
          key={pathname}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
        >
          {children}
        </motion.div>
      </main>
    </div>
  );
}
