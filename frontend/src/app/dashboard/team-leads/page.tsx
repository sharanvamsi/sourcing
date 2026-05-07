'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { api } from '@/lib/api';
import { FunnelIcon, CheckCircleIcon, ClockIcon } from '@heroicons/react/24/outline';

type FilterType = 'all' | 'available' | 'contacted';

export default function TeamLeadsPage() {
  const [leads, setLeads] = useState<any[]>([]);
  const [stats, setStats] = useState({ total: 0, contacted: 0, available: 0 });
  const [isLoading, setIsLoading] = useState(true);
  const [filter, setFilter] = useState<FilterType>('all');
  const [error, setError] = useState('');

  const fetchLeads = async () => {
    try {
      const data = await api.getTeamLeads(filter);
      setLeads(data.leads);
      setStats(data.stats);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchLeads();
  }, [filter]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="loading-spinner" />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Team Leads</h1>
          <p className="text-gray-400 mt-1">Shared lead inventory for your team</p>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="metric-card">
          <div className="text-gray-400 text-sm">Total Leads</div>
          <div className="text-2xl font-bold mt-1">{stats.total}</div>
        </div>
        <div className="metric-card">
          <div className="text-gray-400 text-sm flex items-center gap-1">
            <CheckCircleIcon className="w-4 h-4 text-green-400" />
            Contacted
          </div>
          <div className="text-2xl font-bold mt-1 text-green-400">{stats.contacted}</div>
        </div>
        <div className="metric-card">
          <div className="text-gray-400 text-sm flex items-center gap-1">
            <ClockIcon className="w-4 h-4 text-yellow-400" />
            Available
          </div>
          <div className="text-2xl font-bold mt-1 text-yellow-400">{stats.available}</div>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400">
          {error}
        </div>
      )}

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 mb-4">
        <FunnelIcon className="w-5 h-5 text-gray-400" />
        {(['all', 'available', 'contacted'] as FilterType[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-2 rounded-lg text-sm transition-all ${
              filter === f
                ? 'bg-[#635bff] text-white'
                : 'bg-white/5 text-gray-400 hover:bg-white/10'
            }`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {/* Leads Table */}
      {leads.length === 0 ? (
        <div className="card p-12 text-center">
          <div className="text-gray-400 mb-2">No leads found</div>
          <p className="text-sm text-gray-500">
            {filter === 'all'
              ? 'Your team basket is empty. Search and enrich leads to get started.'
              : `No ${filter} leads in your team basket.`}
          </p>
        </div>
      ) : (
        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Title</th>
                <th>Company</th>
                <th>Email</th>
                <th>Added By</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead, index) => (
                <motion.tr
                  key={lead.apollo_id || index}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: index * 0.02 }}
                >
                  <td className="font-medium">
                    {lead.first_name} {lead.last_name}
                  </td>
                  <td className="text-gray-400">{lead.title || 'N/A'}</td>
                  <td className="text-gray-400">{lead.company || 'N/A'}</td>
                  <td>
                    {lead.email ? (
                      <span className="badge badge-success">{lead.email}</span>
                    ) : (
                      <span className="text-gray-500">No email</span>
                    )}
                  </td>
                  <td className="text-gray-400 text-sm">{lead.added_by || 'Unknown'}</td>
                  <td>
                    {lead.is_contacted ? (
                      <span className="badge badge-success flex items-center gap-1 w-fit">
                        <CheckCircleIcon className="w-3 h-3" />
                        Contacted
                      </span>
                    ) : (
                      <span className="badge badge-warning flex items-center gap-1 w-fit">
                        <ClockIcon className="w-3 h-3" />
                        Available
                      </span>
                    )}
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
