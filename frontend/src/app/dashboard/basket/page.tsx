'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { TrashIcon, SparklesIcon, ArrowDownTrayIcon } from '@heroicons/react/24/outline';

export default function BasketPage() {
  const { refreshUser } = useAuth();
  const [leads, setLeads] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isEnriching, setIsEnriching] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [enrichResult, setEnrichResult] = useState<any>(null);
  const [error, setError] = useState('');

  const fetchBasket = async () => {
    try {
      const data = await api.getBasket();
      setLeads(data.leads);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchBasket();
  }, []);

  const handleClear = async () => {
    setIsClearing(true);
    try {
      await api.clearBasket();
      setLeads([]);
      await refreshUser();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsClearing(false);
    }
  };

  const handleEnrich = async () => {
    setIsEnriching(true);
    setError('');
    setEnrichResult(null);

    try {
      const result = await api.enrichBasket();
      setEnrichResult(result);
      setLeads([]);
      await refreshUser();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsEnriching(false);
    }
  };

  const downloadCSV = () => {
    const headers = ['First Name', 'Last Name', 'Title', 'Company', 'Email'];
    const rows = leads.map((lead) => [
      lead.first_name || '',
      lead.last_name || lead.last_name_obfuscated || '',
      lead.title || '',
      lead.organization?.name || lead.organization_name || lead.company || '',
      lead.email || '',
    ]);

    const csv = [headers, ...rows].map((row) => row.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'leads.csv';
    a.click();
  };

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
          <h1 className="text-2xl font-bold">Your Basket</h1>
          <p className="text-gray-400 mt-1">{leads.length} leads ready for enrichment</p>
        </div>
        {leads.length > 0 && (
          <div className="flex items-center gap-3">
            <button
              onClick={handleClear}
              disabled={isClearing}
              className="btn-secondary flex items-center gap-2"
            >
              {isClearing ? (
                <div className="loading-spinner" />
              ) : (
                <TrashIcon className="w-5 h-5" />
              )}
              Clear Basket
            </button>
            <button
              onClick={handleEnrich}
              disabled={isEnriching}
              className="btn-primary flex items-center gap-2"
            >
              {isEnriching ? (
                <>
                  <div className="loading-spinner" />
                  Enriching...
                </>
              ) : (
                <>
                  <SparklesIcon className="w-5 h-5" />
                  Enrich & Add to Team
                </>
              )}
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="mb-4 p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400">
          {error}
        </div>
      )}

      <AnimatePresence>
        {enrichResult && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mb-6 p-4 rounded-lg bg-green-500/10 border border-green-500/20"
          >
            <h3 className="font-semibold text-green-400 mb-2">Enrichment Complete!</h3>
            <div className="text-sm text-gray-300 space-y-1">
              <p>{enrichResult.enriched_count} leads enriched and added to team basket</p>
              {enrichResult.skipped_duplicates > 0 && (
                <p className="text-yellow-400">
                  {enrichResult.skipped_duplicates} duplicates skipped (already in team basket)
                </p>
              )}
              <p>Credits used: {enrichResult.credits_used}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {leads.length === 0 ? (
        <div className="card p-12 text-center">
          <div className="text-gray-400 mb-2">Your basket is empty</div>
          <p className="text-sm text-gray-500">
            Search for leads and add them to your basket to get started
          </p>
        </div>
      ) : (
        <>
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Title</th>
                  <th>Company</th>
                  <th>Email</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((lead, index) => (
                  <motion.tr
                    key={lead.id || lead.apollo_id || index}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: index * 0.02 }}
                  >
                    <td className="font-medium">
                      {lead.first_name} {lead.last_name || lead.last_name_obfuscated}
                    </td>
                    <td className="text-gray-400">{lead.title}</td>
                    <td className="text-gray-400">
                      {lead.organization?.name || lead.organization_name || lead.company || 'N/A'}
                    </td>
                    <td>
                      {lead.email ? (
                        <span className="badge badge-success">{lead.email}</span>
                      ) : (
                        <span className="text-gray-500">Not enriched</span>
                      )}
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>

          {leads.some((l) => l.email) && (
            <div className="mt-4">
              <button onClick={downloadCSV} className="btn-secondary flex items-center gap-2">
                <ArrowDownTrayIcon className="w-5 h-5" />
                Download CSV
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
