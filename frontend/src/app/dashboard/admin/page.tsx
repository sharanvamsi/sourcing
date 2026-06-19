'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
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
  UserPlusIcon,
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

// ABA teams a member can belong to. Must stay in sync with ALLOWED_TEAMS in
// db_manager.py (the "External" placeholder is assigned automatically).
const ABA_TEAMS = ['BD', 'Finance', 'Marketing', 'Strategy', 'NPO', 'Exec Board'];

type MemberForm = {
  email: string;
  name: string;
  team_name: string;
  role: string;
  is_admin: boolean;
  membership: string;
  blacklist_exempt: boolean;
};

const emptyForm: MemberForm = {
  email: '',
  name: '',
  team_name: ABA_TEAMS[0],
  role: 'consultant',
  is_admin: false,
  membership: 'aba',
  blacklist_exempt: false,
};

export default function AdminPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<'users' | 'teams' | 'analytics'>('users');
  const [users, setUsers] = useState<User[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [analytics, setAnalytics] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');

  // Add/Edit member modal state
  const [modalMode, setModalMode] = useState<'add' | 'edit' | null>(null);
  const [form, setForm] = useState<MemberForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

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

  const openAddMember = () => {
    setForm(emptyForm);
    setFormError('');
    setModalMode('add');
  };

  const openEditMember = (u: User) => {
    setForm({
      email: u.email,
      name: u.name,
      team_name: ABA_TEAMS.includes(u.team_name) ? u.team_name : ABA_TEAMS[0],
      role: u.role,
      is_admin: u.is_admin,
      membership: (u.membership || 'aba') as 'aba' | 'external',
      blacklist_exempt: Boolean(u.blacklist_exempt),
    });
    setFormError('');
    setModalMode('edit');
  };

  const closeModal = () => {
    setModalMode(null);
    setFormError('');
  };

  const handleSubmitMember = async () => {
    setFormError('');
    if (!form.name.trim()) {
      setFormError('Name is required');
      return;
    }
    if (modalMode === 'add' && (!form.email.trim() || !form.email.includes('@'))) {
      setFormError('A valid email is required');
      return;
    }
    if (form.membership === 'aba' && !form.team_name) {
      setFormError('Select a team for ABA members');
      return;
    }

    // External members are not tied to an ABA team; the backend stores a placeholder.
    const team_name = form.membership === 'external' ? 'External' : form.team_name;

    setSaving(true);
    try {
      if (modalMode === 'add') {
        await api.saveUser({
          email: form.email.trim(),
          name: form.name.trim(),
          team_name,
          role: form.role,
          is_admin: form.is_admin,
          membership: form.membership,
          blacklist_exempt: form.blacklist_exempt,
        });
      } else {
        await api.updateUser(form.email, {
          name: form.name.trim(),
          team_name,
          role: form.role,
          is_admin: form.is_admin,
          membership: form.membership,
          blacklist_exempt: form.blacklist_exempt,
        });
      }
      closeModal();
      fetchData();
    } catch (err: any) {
      setFormError(err.message);
    } finally {
      setSaving(false);
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

  const filteredUsers = users.filter((u) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (
      u.name.toLowerCase().includes(q) ||
      u.email.toLowerCase().includes(q) ||
      (u.team_name || '').toLowerCase().includes(q)
    );
  });

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
              <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                <h2 className="text-lg font-semibold">
                  All Users ({filteredUsers.length}
                  {search ? ` of ${users.length}` : ''})
                </h2>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search name, email, team…"
                    className="input py-2 px-3 text-sm w-56"
                  />
                  <button
                    onClick={openAddMember}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#635bff] text-white hover:bg-[#5249e0] transition-all"
                  >
                    <UserPlusIcon className="w-5 h-5" />
                    Add Member
                  </button>
                </div>
              </div>

              {filteredUsers.length === 0 ? (
                <div className="card p-12 text-center">
                  <div className="text-gray-400 mb-2">No members found</div>
                  <p className="text-sm text-gray-500">
                    {search
                      ? 'No members match your search.'
                      : 'Add your first member to get started.'}
                  </p>
                </div>
              ) : (
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
                      {filteredUsers.map((u) => (
                        <motion.tr key={u.email} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                          <td className="font-medium">{u.name}</td>
                          <td className="text-gray-400">{u.email}</td>
                          <td>{u.team_name}</td>
                          <td>
                            <span className="badge">{(u.membership || 'aba').toUpperCase()}</span>
                          </td>
                          <td>
                            <span className={`badge ${u.role === 'pm' ? 'badge-success' : ''}`}>
                              {u.role}
                            </span>
                          </td>
                          <td>
                            {u.is_admin ? (
                              <span className="badge badge-warning">Admin</span>
                            ) : (
                              <span className="text-gray-500">-</span>
                            )}
                          </td>
                          <td>{u.credits_used}</td>
                          <td>
                            <button
                              onClick={() => openEditMember(u)}
                              className="p-1 hover:bg-white/10 rounded"
                              title="Edit member"
                            >
                              <PencilIcon className="w-4 h-4 text-gray-400" />
                            </button>
                          </td>
                        </motion.tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
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

      {/* Add / Edit Member Modal */}
      <AnimatePresence>
        {modalMode && (
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closeModal}
          >
            <motion.div
              className="card w-full max-w-md p-6"
              initial={{ opacity: 0, scale: 0.96, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-5">
                <h3 className="text-lg font-semibold">
                  {modalMode === 'add' ? 'Add Member' : 'Edit Member'}
                </h3>
                <button
                  onClick={closeModal}
                  className="p-1 hover:bg-white/10 rounded text-gray-400"
                >
                  <XMarkIcon className="w-5 h-5" />
                </button>
              </div>

              {formError && (
                <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                  {formError}
                </div>
              )}

              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Email</label>
                  <input
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    disabled={modalMode === 'edit'}
                    placeholder="member@berkeley.edu"
                    className="input w-full py-2 px-3 disabled:opacity-60 disabled:cursor-not-allowed"
                  />
                  {modalMode === 'edit' && (
                    <p className="text-xs text-gray-500 mt-1">Email is the member ID and can’t be changed.</p>
                  )}
                </div>

                <div>
                  <label className="block text-sm text-gray-400 mb-1">Name</label>
                  <input
                    type="text"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="Full name"
                    className="input w-full py-2 px-3"
                  />
                </div>

                <div>
                  <label className="block text-sm text-gray-400 mb-1">Membership</label>
                  <select
                    value={form.membership}
                    onChange={(e) => setForm({ ...form, membership: e.target.value })}
                    className="input w-full py-2 px-3"
                  >
                    <option value="aba">ABA</option>
                    <option value="external">External</option>
                  </select>
                </div>

                {form.membership === 'aba' && (
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Team</label>
                    <select
                      value={form.team_name}
                      onChange={(e) => setForm({ ...form, team_name: e.target.value })}
                      className="input w-full py-2 px-3"
                    >
                      {ABA_TEAMS.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <div>
                  <label className="block text-sm text-gray-400 mb-1">Role</label>
                  <select
                    value={form.role}
                    onChange={(e) => setForm({ ...form, role: e.target.value })}
                    className="input w-full py-2 px-3"
                  >
                    <option value="consultant">Consultant</option>
                    <option value="pm">PM</option>
                  </select>
                </div>

                <div className="flex items-center gap-6 pt-1">
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.is_admin}
                      onChange={(e) => setForm({ ...form, is_admin: e.target.checked })}
                      className="w-4 h-4"
                    />
                    Admin
                  </label>
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.blacklist_exempt}
                      onChange={(e) => setForm({ ...form, blacklist_exempt: e.target.checked })}
                      className="w-4 h-4"
                    />
                    Blacklist exempt
                  </label>
                </div>
              </div>

              <div className="flex justify-end gap-3 mt-6">
                <button
                  onClick={closeModal}
                  disabled={saving}
                  className="btn-secondary py-2 px-4 disabled:opacity-60"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSubmitMember}
                  disabled={saving}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#635bff] text-white hover:bg-[#5249e0] transition-all disabled:opacity-60"
                >
                  {saving && <div className="loading-spinner !w-4 !h-4" />}
                  {modalMode === 'add' ? 'Add Member' : 'Save Changes'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
