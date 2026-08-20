'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import {
  PlusIcon,
  PencilIcon,
  TrashIcon,
  PaperAirplaneIcon,
  EyeIcon,
  ChartBarIcon,
  DocumentTextIcon,
  EnvelopeIcon,
} from '@heroicons/react/24/outline';

type Tab = 'templates' | 'send' | 'campaigns' | 'analytics';

interface Template {
  id: number;
  name: string;
  subject: string;
  body_html: string;
  body_text: string;
  is_active: boolean;
}

export default function EmailOutreachPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<Tab>('templates');
  const [templates, setTemplates] = useState<Template[]>([]);
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [teamLeads, setTeamLeads] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  // Template form state
  const [showTemplateForm, setShowTemplateForm] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<Template | null>(null);
  const [templateForm, setTemplateForm] = useState({
    name: '',
    subject: '',
    body_html: '',
    body_text: '',
  });

  // Send campaign state
  const [selectedLeads, setSelectedLeads] = useState<Set<string>>(new Set());
  const [selectedTemplate, setSelectedTemplate] = useState<number | null>(null);
  const [campaignName, setCampaignName] = useState('');
  const [senderEmail, setSenderEmail] = useState('');
  const [senderName, setSenderName] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [previewContent, setPreviewContent] = useState({ subject: '', body: '' });

  useEffect(() => {
    fetchData();
  }, [activeTab]);

  const fetchData = async () => {
    setIsLoading(true);
    try {
      if (activeTab === 'templates') {
        const data = await api.getTemplates();
        setTemplates(data.templates);
      } else if (activeTab === 'send') {
        const [templatesData, leadsData] = await Promise.all([
          api.getTemplates(),
          api.getTeamLeads('available'),
        ]);
        setTemplates(templatesData.templates);
        setTeamLeads(leadsData.leads);
      } else if (activeTab === 'campaigns' || activeTab === 'analytics') {
        const [campaignsData, statsData] = await Promise.all([
          api.getCampaigns(),
          api.getCampaignStats(),
        ]);
        setCampaigns(campaignsData.campaigns);
        setStats(statsData);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSaveTemplate = async () => {
    try {
      await api.saveTemplate({
        template_id: editingTemplate?.id,
        ...templateForm,
      });
      setShowTemplateForm(false);
      setEditingTemplate(null);
      setTemplateForm({ name: '', subject: '', body_html: '', body_text: '' });
      fetchData();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleDeleteTemplate = async (id: number) => {
    if (!confirm('Are you sure you want to delete this template?')) return;
    try {
      await api.deleteTemplate(id);
      fetchData();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleEditTemplate = (template: Template) => {
    setEditingTemplate(template);
    setTemplateForm({
      name: template.name,
      subject: template.subject,
      body_html: template.body_html,
      body_text: template.body_text,
    });
    setShowTemplateForm(true);
  };

  const handlePreview = async () => {
    if (!selectedTemplate || selectedLeads.size === 0) return;
    const leadId = Array.from(selectedLeads)[0];
    try {
      const data = await api.previewEmail(selectedTemplate, leadId);
      setPreviewContent({ subject: data.subject, body: data.body });
      setShowPreview(true);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleSendCampaign = async () => {
    if (!selectedTemplate || selectedLeads.size === 0 || !campaignName || !senderEmail) {
      setError('Please fill in all required fields');
      return;
    }

    setIsSending(true);
    try {
      await api.sendCampaign({
        name: campaignName,
        template_id: selectedTemplate,
        lead_ids: Array.from(selectedLeads),
        sender_email: senderEmail,
        sender_name: senderName,
      });
      setSelectedLeads(new Set());
      setSelectedTemplate(null);
      setCampaignName('');
      setSenderEmail('');
      setSenderName('');
      setActiveTab('campaigns');
      fetchData();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsSending(false);
    }
  };

  const toggleLeadSelection = (id: string) => {
    const newSet = new Set(selectedLeads);
    if (newSet.has(id)) {
      newSet.delete(id);
    } else {
      newSet.add(id);
    }
    setSelectedLeads(newSet);
  };

  const selectAllLeads = () => {
    setSelectedLeads(new Set(teamLeads.map((l) => l.apollo_id)));
  };

  const deselectAllLeads = () => {
    setSelectedLeads(new Set());
  };

  if (user?.role !== 'pm') {
    return (
      <div className="card p-12 text-center">
        <div className="text-gray-400 mb-2">Access Denied</div>
        <p className="text-sm text-gray-500">
          Email Outreach is only available to Project Managers.
        </p>
      </div>
    );
  }

  const tabs = [
    { id: 'templates' as Tab, name: 'Templates', icon: DocumentTextIcon },
    { id: 'send' as Tab, name: 'Send Campaign', icon: PaperAirplaneIcon },
    { id: 'campaigns' as Tab, name: 'Campaigns', icon: EnvelopeIcon },
    { id: 'analytics' as Tab, name: 'Analytics', icon: ChartBarIcon },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Email Outreach</h1>

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
                ? 'bg-[#3B82F6] text-white'
                : 'bg-[#161616] text-gray-400 hover:bg-[#1F1F1F]'
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
          {/* Templates Tab */}
          {activeTab === 'templates' && (
            <div>
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-semibold">Email Templates</h2>
                <button
                  onClick={() => {
                    setEditingTemplate(null);
                    setTemplateForm({ name: '', subject: '', body_html: '', body_text: '' });
                    setShowTemplateForm(true);
                  }}
                  className="btn-primary flex items-center gap-2"
                >
                  <PlusIcon className="w-5 h-5" />
                  New Template
                </button>
              </div>

              {templates.length === 0 ? (
                <div className="card p-12 text-center">
                  <div className="text-gray-400 mb-2">No templates yet</div>
                  <p className="text-sm text-gray-500">
                    Create your first email template to get started.
                  </p>
                </div>
              ) : (
                <div className="grid gap-4">
                  {templates.map((template) => (
                    <motion.div
                      key={template.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="card p-4"
                    >
                      <div className="flex justify-between items-start">
                        <div>
                          <h3 className="font-semibold">{template.name}</h3>
                          <p className="text-sm text-gray-400 mt-1">Subject: {template.subject}</p>
                        </div>
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleEditTemplate(template)}
                            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
                          >
                            <PencilIcon className="w-4 h-4 text-gray-400" />
                          </button>
                          <button
                            onClick={() => handleDeleteTemplate(template.id)}
                            className="p-2 hover:bg-red-500/20 rounded-lg transition-colors"
                          >
                            <TrashIcon className="w-4 h-4 text-red-400" />
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              )}

              {/* Template Form Modal */}
              <AnimatePresence>
                {showTemplateForm && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
                    onClick={() => setShowTemplateForm(false)}
                  >
                    <motion.div
                      initial={{ scale: 0.95 }}
                      animate={{ scale: 1 }}
                      exit={{ scale: 0.95 }}
                      className="card p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <h2 className="text-xl font-semibold mb-4">
                        {editingTemplate ? 'Edit Template' : 'New Template'}
                      </h2>

                      <div className="space-y-4">
                        <div>
                          <label className="block text-sm text-gray-400 mb-2">Template Name</label>
                          <input
                            type="text"
                            value={templateForm.name}
                            onChange={(e) =>
                              setTemplateForm({ ...templateForm, name: e.target.value })
                            }
                            className="input"
                            placeholder="e.g., Initial Outreach"
                          />
                        </div>

                        <div>
                          <label className="block text-sm text-gray-400 mb-2">Subject Line</label>
                          <input
                            type="text"
                            value={templateForm.subject}
                            onChange={(e) =>
                              setTemplateForm({ ...templateForm, subject: e.target.value })
                            }
                            className="input"
                            placeholder="e.g., {{first_name}}, quick question about {{company}}"
                          />
                        </div>

                        <div>
                          <label className="block text-sm text-gray-400 mb-2">
                            Email Body (HTML)
                          </label>
                          <textarea
                            value={templateForm.body_html}
                            onChange={(e) =>
                              setTemplateForm({ ...templateForm, body_html: e.target.value })
                            }
                            className="input min-h-[200px] font-mono text-sm"
                            placeholder="Hi {{first_name}},&#10;&#10;I noticed you're working at {{company}}..."
                          />
                        </div>

                        <div>
                          <label className="block text-sm text-gray-400 mb-2">
                            Plain Text Version
                          </label>
                          <textarea
                            value={templateForm.body_text}
                            onChange={(e) =>
                              setTemplateForm({ ...templateForm, body_text: e.target.value })
                            }
                            className="input min-h-[100px] font-mono text-sm"
                            placeholder="Plain text fallback..."
                          />
                        </div>

                        <div className="bg-white/5 rounded-lg p-3 text-sm text-gray-400">
                          <strong>Available variables:</strong> {`{{first_name}}`},{' '}
                          {`{{last_name}}`}, {`{{company}}`}, {`{{title}}`}, {`{{email}}`}
                        </div>
                      </div>

                      <div className="flex justify-end gap-3 mt-6">
                        <button
                          onClick={() => setShowTemplateForm(false)}
                          className="btn-secondary"
                        >
                          Cancel
                        </button>
                        <button onClick={handleSaveTemplate} className="btn-primary">
                          {editingTemplate ? 'Update' : 'Create'} Template
                        </button>
                      </div>
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {/* Send Campaign Tab */}
          {activeTab === 'send' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Lead Selection */}
              <div>
                <div className="flex justify-between items-center mb-4">
                  <h2 className="text-lg font-semibold">Select Leads ({selectedLeads.size})</h2>
                  <div className="flex gap-2">
                    <button onClick={selectAllLeads} className="btn-secondary text-sm py-1 px-3">
                      Select All
                    </button>
                    <button onClick={deselectAllLeads} className="btn-secondary text-sm py-1 px-3">
                      Clear
                    </button>
                  </div>
                </div>

                {teamLeads.length === 0 ? (
                  <div className="card p-8 text-center">
                    <div className="text-gray-400">No available leads</div>
                    <p className="text-sm text-gray-500 mt-1">
                      All leads have been contacted or the team basket is empty.
                    </p>
                  </div>
                ) : (
                  <div className="card max-h-[400px] overflow-y-auto">
                    {teamLeads.map((lead) => (
                      <div
                        key={lead.apollo_id}
                        onClick={() => toggleLeadSelection(lead.apollo_id)}
                        className={`p-3 border-b border-white/5 cursor-pointer transition-colors ${
                          selectedLeads.has(lead.apollo_id) ? 'bg-blue-500/10' : 'hover:bg-[#161616]'
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <div
                            className={`w-4 h-4 rounded border-2 flex items-center justify-center ${
                              selectedLeads.has(lead.apollo_id)
                                ? 'bg-[#3B82F6] border-[#3B82F6]'
                                : 'border-gray-600'
                            }`}
                          >
                            {selectedLeads.has(lead.apollo_id) && (
                              <div className="w-2 h-2 bg-white rounded-sm" />
                            )}
                          </div>
                          <div>
                            <div className="font-medium">
                              {lead.first_name} {lead.last_name}
                            </div>
                            <div className="text-sm text-gray-400">
                              {lead.email || 'No email'} • {lead.company || 'N/A'}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Campaign Settings */}
              <div>
                <h2 className="text-lg font-semibold mb-4">Campaign Settings</h2>
                <div className="card p-4 space-y-4">
                  <div>
                    <label className="block text-sm text-gray-400 mb-2">Campaign Name</label>
                    <input
                      type="text"
                      value={campaignName}
                      onChange={(e) => setCampaignName(e.target.value)}
                      className="input"
                      placeholder="e.g., Q1 Outreach"
                    />
                  </div>

                  <div>
                    <label className="block text-sm text-gray-400 mb-2">Email Template</label>
                    <select
                      value={selectedTemplate || ''}
                      onChange={(e) => setSelectedTemplate(Number(e.target.value) || null)}
                      className="input"
                    >
                      <option value="">Select a template...</option>
                      {templates.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm text-gray-400 mb-2">Sender Email</label>
                    <input
                      type="email"
                      value={senderEmail}
                      onChange={(e) => setSenderEmail(e.target.value)}
                      className="input"
                      placeholder="you@yourcompany.com"
                    />
                  </div>

                  <div>
                    <label className="block text-sm text-gray-400 mb-2">Sender Name</label>
                    <input
                      type="text"
                      value={senderName}
                      onChange={(e) => setSenderName(e.target.value)}
                      className="input"
                      placeholder="Your Name"
                    />
                  </div>

                  <div className="flex gap-3 pt-4">
                    <button
                      onClick={handlePreview}
                      disabled={!selectedTemplate || selectedLeads.size === 0}
                      className="btn-secondary flex items-center gap-2"
                    >
                      <EyeIcon className="w-5 h-5" />
                      Preview
                    </button>
                    <button
                      onClick={handleSendCampaign}
                      disabled={isSending || selectedLeads.size === 0 || !selectedTemplate}
                      className="btn-primary flex items-center gap-2"
                    >
                      {isSending ? (
                        <>
                          <div className="loading-spinner" />
                          Sending...
                        </>
                      ) : (
                        <>
                          <PaperAirplaneIcon className="w-5 h-5" />
                          Send to {selectedLeads.size} Leads
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>

              {/* Preview Modal */}
              <AnimatePresence>
                {showPreview && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
                    onClick={() => setShowPreview(false)}
                  >
                    <motion.div
                      initial={{ scale: 0.95 }}
                      animate={{ scale: 1 }}
                      exit={{ scale: 0.95 }}
                      className="card p-6 w-full max-w-2xl"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <h2 className="text-xl font-semibold mb-4">Email Preview</h2>
                      <div className="bg-white/5 rounded-lg p-4 mb-4">
                        <div className="text-sm text-gray-400 mb-1">Subject:</div>
                        <div className="font-medium">{previewContent.subject}</div>
                      </div>
                      <div className="bg-white/5 rounded-lg p-4">
                        <div className="text-sm text-gray-400 mb-1">Body:</div>
                        <div
                          className="prose prose-invert max-w-none"
                          dangerouslySetInnerHTML={{ __html: previewContent.body }}
                        />
                      </div>
                      <button
                        onClick={() => setShowPreview(false)}
                        className="btn-secondary mt-4"
                      >
                        Close
                      </button>
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {/* Campaigns Tab */}
          {activeTab === 'campaigns' && (
            <div>
              <h2 className="text-lg font-semibold mb-4">Campaign History</h2>
              {campaigns.length === 0 ? (
                <div className="card p-12 text-center">
                  <div className="text-gray-400 mb-2">No campaigns yet</div>
                  <p className="text-sm text-gray-500">
                    Send your first campaign to see it here.
                  </p>
                </div>
              ) : (
                <div className="table-container">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Campaign</th>
                        <th>Status</th>
                        <th>Sent</th>
                        <th>Opened</th>
                        <th>Clicked</th>
                        <th>Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {campaigns.map((campaign) => (
                        <tr key={campaign.id}>
                          <td className="font-medium">{campaign.name}</td>
                          <td>
                            <span
                              className={`badge ${
                                campaign.status === 'sent'
                                  ? 'badge-success'
                                  : campaign.status === 'sending'
                                  ? 'badge-warning'
                                  : ''
                              }`}
                            >
                              {campaign.status}
                            </span>
                          </td>
                          <td>{campaign.sent_count || 0}</td>
                          <td>{campaign.opened_count || 0}</td>
                          <td>{campaign.clicked_count || 0}</td>
                          <td className="text-gray-400">
                            {new Date(campaign.created_at).toLocaleDateString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Analytics Tab */}
          {activeTab === 'analytics' && stats && (
            <div>
              <h2 className="text-lg font-semibold mb-4">Email Analytics</h2>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                <div className="metric-card">
                  <div className="text-gray-400 text-sm">Total Sent</div>
                  <div className="text-2xl font-bold mt-1">{stats.total_sent || 0}</div>
                </div>
                <div className="metric-card">
                  <div className="text-gray-400 text-sm">Delivered</div>
                  <div className="text-2xl font-bold mt-1 text-green-400">
                    {stats.total_delivered || 0}
                  </div>
                </div>
                <div className="metric-card">
                  <div className="text-gray-400 text-sm">Open Rate</div>
                  <div className="text-2xl font-bold mt-1 text-blue-400">
                    {stats.open_rate ? `${(stats.open_rate * 100).toFixed(1)}%` : '0%'}
                  </div>
                </div>
                <div className="metric-card">
                  <div className="text-gray-400 text-sm">Click Rate</div>
                  <div className="text-2xl font-bold mt-1 text-purple-400">
                    {stats.click_rate ? `${(stats.click_rate * 100).toFixed(1)}%` : '0%'}
                  </div>
                </div>
              </div>

              {stats.by_campaign && stats.by_campaign.length > 0 && (
                <div>
                  <h3 className="font-semibold mb-3">Performance by Campaign</h3>
                  <div className="table-container">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Campaign</th>
                          <th>Sent</th>
                          <th>Opened</th>
                          <th>Open Rate</th>
                          <th>Clicked</th>
                          <th>Click Rate</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stats.by_campaign.map((c: any) => (
                          <tr key={c.id}>
                            <td className="font-medium">{c.name}</td>
                            <td>{c.sent}</td>
                            <td>{c.opened}</td>
                            <td>
                              {c.sent > 0 ? `${((c.opened / c.sent) * 100).toFixed(1)}%` : '0%'}
                            </td>
                            <td>{c.clicked}</td>
                            <td>
                              {c.sent > 0 ? `${((c.clicked / c.sent) * 100).toFixed(1)}%` : '0%'}
                            </td>
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
