'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { MagnifyingGlassIcon, PlusIcon, CheckIcon } from '@heroicons/react/24/outline';

const seniorityOptions = [
  { value: 'senior', label: 'Senior' },
  { value: 'manager', label: 'Manager' },
  { value: 'director', label: 'Director' },
  { value: 'head', label: 'Head' },
  { value: 'vp', label: 'VP' },
  { value: 'c_level', label: 'C-Level' },
  { value: 'partner', label: 'Partner' },
  { value: 'owner', label: 'Owner' },
];

export default function SearchPage() {
  const { refreshUser } = useAuth();
  const [domain, setDomain] = useState('');
  const [titles, setTitles] = useState('');
  const [locations, setLocations] = useState('');
  const [seniority, setSeniority] = useState<string[]>([]);
  const [maxResults, setMaxResults] = useState(25);
  const [isSearching, setIsSearching] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [resolvedDomain, setResolvedDomain] = useState('');
  const [error, setError] = useState('');
  const [isAdding, setIsAdding] = useState(false);

  const handleSearch = async () => {
    if (!domain.trim()) {
      setError('Please enter a company domain or name');
      return;
    }
    setError('');
    setIsSearching(true);
    setResults([]);
    setSelectedIds(new Set());

    try {
      const data = await api.search({
        domain: domain.trim(),
        job_titles: titles ? titles.split(',').map(t => t.trim()).filter(Boolean) : [],
        locations: locations ? locations.split(',').map(l => l.trim()).filter(Boolean) : [],
        seniority,
        max_results: maxResults,
      });
      setResults(data.results);
      setResolvedDomain(data.resolved_domain);
      // Select all by default
      setSelectedIds(new Set(data.results.map((r: any) => r.id)));
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsSearching(false);
    }
  };

  const toggleSelect = (id: string) => {
    const newSet = new Set(selectedIds);
    if (newSet.has(id)) {
      newSet.delete(id);
    } else {
      newSet.add(id);
    }
    setSelectedIds(newSet);
  };

  const selectAll = () => {
    setSelectedIds(new Set(results.map(r => r.id)));
  };

  const deselectAll = () => {
    setSelectedIds(new Set());
  };

  const addToBasket = async () => {
    const selectedLeads = results.filter(r => selectedIds.has(r.id));
    if (selectedLeads.length === 0) return;

    setIsAdding(true);
    try {
      await api.addToBasket(selectedLeads);
      await refreshUser();
      setResults([]);
      setSelectedIds(new Set());
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsAdding(false);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Search Leads</h1>

      {/* Search Form */}
      <div className="card p-6 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          <div className="lg:col-span-2">
            <label className="block text-sm text-gray-400 mb-2">Company Domain / Name</label>
            <input
              type="text"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              className="input"
              placeholder="e.g., apple.com or Apple"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Max Results</label>
            <input
              type="number"
              value={maxResults}
              onChange={(e) => setMaxResults(Number(e.target.value))}
              className="input"
              min={1}
              max={150}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <div>
            <label className="block text-sm text-gray-400 mb-2">Job Titles (comma separated)</label>
            <input
              type="text"
              value={titles}
              onChange={(e) => setTitles(e.target.value)}
              className="input"
              placeholder="e.g., Engineer, Manager"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Locations (comma separated)</label>
            <input
              type="text"
              value={locations}
              onChange={(e) => setLocations(e.target.value)}
              className="input"
              placeholder="e.g., San Francisco, New York"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Seniority</label>
            <div className="flex flex-wrap gap-2">
              {seniorityOptions.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => {
                    if (seniority.includes(opt.value)) {
                      setSeniority(seniority.filter(s => s !== opt.value));
                    } else {
                      setSeniority([...seniority, opt.value]);
                    }
                  }}
                  className={`px-3 py-1 rounded-full text-xs transition-all ${
                    seniority.includes(opt.value)
                      ? 'bg-[#635bff] text-white'
                      : 'bg-white/5 text-gray-400 hover:bg-white/10'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            {error}
          </div>
        )}

        <button
          onClick={handleSearch}
          disabled={isSearching}
          className="btn-primary flex items-center gap-2"
        >
          {isSearching ? (
            <>
              <div className="loading-spinner" />
              Searching...
            </>
          ) : (
            <>
              <MagnifyingGlassIcon className="w-5 h-5" />
              Search Leads
            </>
          )}
        </button>
      </div>

      {/* Results */}
      <AnimatePresence>
        {results.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
          >
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold">
                  Found {results.length} leads
                  {resolvedDomain && resolvedDomain !== domain && (
                    <span className="text-gray-400 font-normal ml-2">
                      (resolved to {resolvedDomain})
                    </span>
                  )}
                </h2>
                <p className="text-sm text-gray-400">{selectedIds.size} selected</p>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={selectAll} className="btn-secondary text-sm py-2 px-4">
                  Select All
                </button>
                <button onClick={deselectAll} className="btn-secondary text-sm py-2 px-4">
                  Deselect All
                </button>
                <button
                  onClick={addToBasket}
                  disabled={selectedIds.size === 0 || isAdding}
                  className="btn-primary flex items-center gap-2"
                >
                  {isAdding ? (
                    <>
                      <div className="loading-spinner" />
                      Adding...
                    </>
                  ) : (
                    <>
                      <PlusIcon className="w-5 h-5" />
                      Add {selectedIds.size} to Basket
                    </>
                  )}
                </button>
              </div>
            </div>

            <div className="table-container">
              <table className="table">
                <thead>
                  <tr>
                    <th className="w-12"></th>
                    <th>Name</th>
                    <th>Title</th>
                    <th>Company</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((person) => (
                    <motion.tr
                      key={person.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="cursor-pointer"
                      onClick={() => toggleSelect(person.id)}
                    >
                      <td>
                        <div
                          className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-all ${
                            selectedIds.has(person.id)
                              ? 'bg-[#635bff] border-[#635bff]'
                              : 'border-gray-600'
                          }`}
                        >
                          {selectedIds.has(person.id) && (
                            <CheckIcon className="w-3 h-3 text-white" />
                          )}
                        </div>
                      </td>
                      <td className="font-medium">
                        {person.first_name} {person.last_name_obfuscated || person.last_name}
                      </td>
                      <td className="text-gray-400">{person.title}</td>
                      <td className="text-gray-400">
                        {person.organization?.name || 'N/A'}
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
