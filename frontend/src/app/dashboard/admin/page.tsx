'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import {
  UsersIcon,
  BuildingOfficeIcon,
  CreditCardIcon,
  ChartBarIcon,
  PencilIcon,
  CheckIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

interface User {
  email: string;
  name: string;
  team_name: string;
  role: string;
  is_admin: boolean;
  credits_used: number;
  membership?: string;
  blacklist_exempt?: boolean;
}

interface Team {
  name: string;
  total_credits: number;
  used_credits: number;
  member_count: number;
}

export default function AdminPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<'users' | 'teams' | 'analytics'>('users');
  const [users, setUsers] = useState<User[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [analytics, setAnalytics] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  // Edit user state
  const [editingUser, setEditingUser] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({
    role: '',
    is_admin: false,
    membership: 'aba',
    blacklist_exempt: false,
  });

  // Add credits state
  const [addingCredits, setAddingCredits] = useState<string | null>(null);
  const [creditsAmount, setCreditsAmount] = useState(0);

  useEffect(() => {
    fetchData();
  }, [activeTab]);

  const fetchData = async () => {
    setIsLoading(true);
    try {
      if (activeTab === 'users') {
        const data = await api.getUsers();
        setUsers(data.users);
      } else if (activeTab === 'teams') {
        const data = await api.getTeams();
        setTeams(data.teams);
      } else if (activeTab === 'analytics') {
        const data = await api.getAdminAnalytics();
        setAnalytics(data);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleEditUser = (u: User) => {
    setEditingUser(u.email);
    setEditForm({
      role: u.role,
      is_admin: u.is_admin,
      membership: (u.membership || 'aba') as 'aba' | 'external',
      blacklist_exempt: Boolean(u.blacklist_exempt),
    });
  };

  const handleSaveUser = async (email: string) => {
    try {
      await api.updateUser(email, editForm);
      setEditingUser(null);
      fetchData();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleAddCredits = async (teamName: string) => {
    if (creditsAmount <= 0) return;
    try {
      await api.addTeamCredits(teamName, creditsAmount);
      setAddingCredits(null);
      setCreditsAmount(0);
      fetchData();
    } catch (err: any) {
      setError(err.message);
    }
  };

  if (!user?.is_admin) {
    return (
      <div className="card p-12 text-center">
        <div className="text-gray-400 mb-2">Access Denied</div>
        <p className="text-sm text-gray-500">Admin access required.</p>
      </div>
    );
  }

  const tabs = [
    { id: 'users' as const, name: 'Users', icon: UsersIcon },
    { id: 'teams' as const, name: 'Teams', icon: BuildingOfficeIcon },
    { id: 'analytics' as const, name: 'Analytics', icon: ChartBarIcon },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Admin Dashboard</h1>

      {error && (
        <div className="mb-4 p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400">
          {error}
          <button onClick={() => setError('')} className="ml-2 underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 mb-6 border-b border-white/10 pb-4">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${
              activeTab === tab.id
                ? 'bg-[#635bff] text-white'
                : 'bg-white/5 text-gray-400 hover:bg-white/10'
            }`}
          >
            <tab.icon className="w-5 h-5" />
            {tab.name}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <div className="loading-spinner" />
        </div>
      ) : (
        <>
          {/* Users Tab */}
          {activeTab === 'users' && (
            <div>
              <h2 className="text-lg font-semibold mb-4">All Users ({users.length})</h2>
              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Email</th>
                      <th>Team</th>
                      <th>Membership</th>
                      <th>Role</th>
                      <th>Admin</th>
                      <th>Credits Used</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <motion.tr
                        key={u.email}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                      >
                        <td className="font-medium">{u.name}</td>
                        <td className="text-gray-400">{u.email}</td>
                        <td>{u.team_name}</td>
                        <td>
                          {editingUser === u.email ? (
                            <select
                              value={editForm.membership}
                              onChange={(e) =>
                                setEditForm({ ...editForm, membership: e.target.value })
                              }
                              className="input py-1 px-2 text-sm"
                            >
                              <option value="aba">ABA</option>
                              <option value="external">External</option>
                            </select>
                          ) : (
                            <span className="badge">{(u.membership || 'aba').toUpperCase()}</span>
                          )}
                        </td>
                        <td>
                          {editingUser === u.email ? (
                            <select
                              value={editForm.role}
                              onChange={(e) =>
                                setEditForm({ ...editForm, role: e.target.value })
                              }
                              className="input py-1 px-2 text-sm"
                            >
                              <option value="consultant">Consultant</option>
                              <option value="pm">PM</option>
                            </select>
                          ) : (
                            <span
                              className={`badge ${
                                u.role === 'pm' ? 'badge-success' : ''
                              }`}
                            >
                              {u.role}
                            </span>
                          )}
                        </td>
                        <td>
                          {editingUser === u.email ? (
                            <input
                              type="checkbox"
                              checked={editForm.is_admin}
                              onChange={(e) =>
                                setEditForm({ ...editForm, is_admin: e.target.checked })
                              }
                              className="w-4 h-4"
                            />
                          ) : u.is_admin ? (
                            <span className="badge badge-warning">Admin</span>
                          ) : (
                            <span className="text-gray-500">-</span>
                          )}
                        </td>
                        <td>{u.credits_used}</td>
                        <td>
                          {editingUser === u.email ? (
                            <div className="flex gap-2">
                              <button
                                onClick={() => handleSaveUser(u.email)}
                                className="p-1 hover:bg-green-500/20 rounded"
                              >
                                <CheckIcon className="w-4 h-4 text-green-400" />
                              </button>
                              <button
                                onClick={() => setEditingUser(null)}
                                className="p-1 hover:bg-red-500/20 rounded"
                              >
                                <XMarkIcon className="w-4 h-4 text-red-400" />
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => handleEditUser(u)}
                              className="p-1 hover:bg-white/10 rounded"
                            >
                              <PencilIcon className="w-4 h-4 text-gray-400" />
                            </button>
                          )}
                        </td>
                      </motion.tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Teams Tab */}
          {activeTab === 'teams' && (
            <div>
              <h2 className="text-lg font-semibold mb-4">All Teams ({teams.length})</h2>
              <div className="grid gap-4">
                {teams.map((team) => (
                  <motion.div
                    key={team.name}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="card p-4"
                  >
                    <div className="flex justify-between items-center">
                      <div>
                        <h3 className="font-semibold text-lg">{team.name}</h3>
                        <p className="text-sm text-gray-400">{team.member_count} members</p>
                      </div>
                      <div className="flex items-center gap-6">
                        <div className="text-right">
                          <div className="text-sm text-gray-400">Credits</div>
                          <div className="font-semibold">
                            {team.used_credits} / {team.total_credits}
                          </div>
                          <div className="w-32 h-2 bg-white/10 rounded-full mt-1">
                            <div
                              className="h-full bg-[#635bff] rounded-full"
                              style={{
                                width: `${Math.min(
                                  (team.used_credits / team.total_credits) * 100,
                                  100
                                )}%`,
                              }}
                            />
                          </div>
                        </div>
                        {addingCredits === team.name ? (
                          <div className="flex items-center gap-2">
                            <input
                              type="number"
                              value={creditsAmount}
                              onChange={(e) => setCreditsAmount(Number(e.target.value))}
                              className="input w-24 py-1"
                              placeholder="Amount"
                              min={1}
                            />
                            <button
                              onClick={() => handleAddCredits(team.name)}
                              className="p-1 hover:bg-green-500/20 rounded"
                            >
                              <CheckIcon className="w-5 h-5 text-green-400" />
                            </button>
                            <button
                              onClick={() => {
                                setAddingCredits(null);
                                setCreditsAmount(0);
                              }}
                              className="p-1 hover:bg-red-500/20 rounded"
                            >
                              <XMarkIcon className="w-5 h-5 text-red-400" />
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setAddingCredits(team.name)}
                            className="btn-secondary flex items-center gap-2 py-2"
                          >
                            <CreditCardIcon className="w-4 h-4" />
                            Add Credits
                          </button>
                        )}
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>
          )}

          {/* Analytics Tab */}
          {activeTab === 'analytics' && analytics && (
            <div>
              <h2 className="text-lg font-semibold mb-4">Platform Analytics</h2>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                <div className="metric-card">
                  <div className="text-gray-400 text-sm">Total Users</div>
                  <div className="text-2xl font-bold mt-1">{analytics.total_users}</div>
                </div>
                <div className="metric-card">
                  <div className="text-gray-400 text-sm">Total Teams</div>
                  <div className="text-2xl font-bold mt-1">{analytics.total_teams}</div>
                </div>
                <div className="metric-card">
                  <div className="text-gray-400 text-sm">Total Leads</div>
                  <div className="text-2xl font-bold mt-1">{analytics.total_leads}</div>
                </div>
                <div className="metric-card">
                  <div className="text-gray-400 text-sm">Total Credits Used</div>
                  <div className="text-2xl font-bold mt-1">{analytics.total_credits_used}</div>
                </div>
              </div>

              {analytics.top_users && analytics.top_users.length > 0 && (
                <div className="mb-6">
                  <h3 className="font-semibold mb-3">Top Users by Credits</h3>
                  <div className="table-container">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>User</th>
                          <th>Team</th>
                          <th>Credits Used</th>
                        </tr>
                      </thead>
                      <tbody>
                        {analytics.top_users.map((u: any, i: number) => (
                          <tr key={u.email}>
                            <td className="font-medium">
                              <span className="text-gray-500 mr-2">#{i + 1}</span>
                              {u.name}
                            </td>
                            <td className="text-gray-400">{u.team_name}</td>
                            <td>{u.credits_used}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {analytics.top_teams && analytics.top_teams.length > 0 && (
                <div>
                  <h3 className="font-semibold mb-3">Top Teams by Credits</h3>
                  <div className="table-container">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Team</th>
                          <th>Members</th>
                          <th>Credits Used</th>
                          <th>Total Credits</th>
                        </tr>
                      </thead>
                      <tbody>
                        {analytics.top_teams.map((t: any, i: number) => (
                          <tr key={t.name}>
                            <td className="font-medium">
                              <span className="text-gray-500 mr-2">#{i + 1}</span>
                              {t.name}
                            </td>
                            <td className="text-gray-400">{t.member_count}</td>
                            <td>{t.used_credits}</td>
                            <td>{t.total_credits}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
