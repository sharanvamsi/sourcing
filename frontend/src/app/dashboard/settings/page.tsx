'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import {
  KeyIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  EyeIcon,
  EyeSlashIcon,
} from '@heroicons/react/24/outline';

export default function SettingsPage() {
  const { user } = useAuth();
  const [apolloKey, setApolloKey] = useState('');
  const [sendgridKey, setSendgridKey] = useState('');
  const [showApolloKey, setShowApolloKey] = useState(false);
  const [showSendgridKey, setShowSendgridKey] = useState(false);
  const [hasApolloKey, setHasApolloKey] = useState(false);
  const [hasSendgridKey, setHasSendgridKey] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const data = await api.getSettings();
      setHasApolloKey(data.has_apollo_key);
      setHasSendgridKey(data.has_sendgrid_key);
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message });
    } finally {
      setIsLoading(false);
    }
  };

  const handleSaveApolloKey = async () => {
    if (!apolloKey.trim()) return;
    setIsSaving(true);
    try {
      await api.saveApolloKey(apolloKey);
      setApolloKey('');
      setHasApolloKey(true);
      setMessage({ type: 'success', text: 'Apollo API key saved successfully!' });
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message });
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveSendgridKey = async () => {
    if (!sendgridKey.trim()) return;
    setIsSaving(true);
    try {
      await api.saveSendgridKey(sendgridKey);
      setSendgridKey('');
      setHasSendgridKey(true);
      setMessage({ type: 'success', text: 'SendGrid API key saved successfully!' });
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message });
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="loading-spinner" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-6">Settings</h1>

      {message.text && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className={`mb-6 p-4 rounded-lg flex items-center gap-2 ${
            message.type === 'success'
              ? 'bg-green-500/10 border border-green-500/20 text-green-400'
              : 'bg-red-500/10 border border-red-500/20 text-red-400'
          }`}
        >
          {message.type === 'success' ? (
            <CheckCircleIcon className="w-5 h-5" />
          ) : (
            <ExclamationCircleIcon className="w-5 h-5" />
          )}
          {message.text}
        </motion.div>
      )}

      {/* Profile Section */}
      <div className="card p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">Profile</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Name</label>
            <div className="font-medium">{user?.name}</div>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Email</label>
            <div className="font-medium">{user?.email}</div>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Team</label>
            <div className="font-medium">{user?.team_name}</div>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Role</label>
            <div>
              <span className={`badge ${user?.role === 'pm' ? 'badge-success' : ''}`}>
                {user?.role === 'pm' ? 'Project Manager' : 'Consultant'}
              </span>
              {user?.is_admin && (
                <span className="badge badge-warning ml-2">Admin</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* API Keys Section */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <KeyIcon className="w-5 h-5" />
          API Keys
        </h2>
        <p className="text-sm text-gray-400 mb-6">
          Your API keys are encrypted and stored securely. They are never shared with other users.
        </p>

        {/* Apollo API Key */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-2">
            <label className="block text-sm font-medium">Apollo API Key</label>
            {hasApolloKey && (
              <span className="flex items-center gap-1 text-green-400 text-sm">
                <CheckCircleIcon className="w-4 h-4" />
                Configured
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                type={showApolloKey ? 'text' : 'password'}
                value={apolloKey}
                onChange={(e) => setApolloKey(e.target.value)}
                className="input pr-10"
                placeholder={hasApolloKey ? '••••••••••••••••' : 'Enter your Apollo API key'}
              />
              <button
                type="button"
                onClick={() => setShowApolloKey(!showApolloKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
              >
                {showApolloKey ? (
                  <EyeSlashIcon className="w-5 h-5" />
                ) : (
                  <EyeIcon className="w-5 h-5" />
                )}
              </button>
            </div>
            <button
              onClick={handleSaveApolloKey}
              disabled={!apolloKey.trim() || isSaving}
              className="btn-primary"
            >
              {isSaving ? 'Saving...' : hasApolloKey ? 'Update' : 'Save'}
            </button>
          </div>
          <p className="text-xs text-gray-500 mt-2">
            Get your API key from{' '}
            <a
              href="https://app.apollo.io/#/settings/integrations/api"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#635bff] hover:underline"
            >
              Apollo Settings
            </a>
          </p>
        </div>

        {/* SendGrid API Key (PM only) */}
        {user?.role === 'pm' && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium">SendGrid API Key</label>
              {hasSendgridKey && (
                <span className="flex items-center gap-1 text-green-400 text-sm">
                  <CheckCircleIcon className="w-4 h-4" />
                  Configured
                </span>
              )}
            </div>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type={showSendgridKey ? 'text' : 'password'}
                  value={sendgridKey}
                  onChange={(e) => setSendgridKey(e.target.value)}
                  className="input pr-10"
                  placeholder={hasSendgridKey ? '••••••••••••••••' : 'Enter your SendGrid API key'}
                />
                <button
                  type="button"
                  onClick={() => setShowSendgridKey(!showSendgridKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
                >
                  {showSendgridKey ? (
                    <EyeSlashIcon className="w-5 h-5" />
                  ) : (
                    <EyeIcon className="w-5 h-5" />
                  )}
                </button>
              </div>
              <button
                onClick={handleSaveSendgridKey}
                disabled={!sendgridKey.trim() || isSaving}
                className="btn-primary"
              >
                {isSaving ? 'Saving...' : hasSendgridKey ? 'Update' : 'Save'}
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              Get your API key from{' '}
              <a
                href="https://app.sendgrid.com/settings/api_keys"
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#635bff] hover:underline"
              >
                SendGrid Settings
              </a>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
