const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class ApiClient {
  private token: string | null = null;

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('token', token);
    } else {
      localStorage.removeItem('token');
    }
  }

  getToken(): string | null {
    if (this.token) return this.token;
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('token');
    }
    return this.token;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const token = this.getToken();
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    };

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  }

  // Auth
  async login(email: string, password: string) {
    const data = await this.request<{ access_token: string; user: any }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(data.access_token);
    return data;
  }

  async getMe() {
    return this.request<{ user: any; credits_used: number; team_credits: number; basket_count: number }>(
      '/api/auth/me'
    );
  }

  logout() {
    this.setToken(null);
  }

  // Search
  async search(params: {
    domain: string;
    job_titles?: string[];
    locations?: string[];
    seniority?: string[];
    max_results?: number;
  }) {
    return this.request<{ results: any[]; count: number; resolved_domain: string }>('/api/search', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  }

  // Basket
  async getBasket() {
    return this.request<{ leads: any[]; count: number }>('/api/basket');
  }

  async addToBasket(leads: any[]) {
    return this.request<{ added: number; total: number }>('/api/basket/add', {
      method: 'POST',
      body: JSON.stringify({ leads }),
    });
  }

  async clearBasket() {
    return this.request<{ success: boolean }>('/api/basket/clear', {
      method: 'DELETE',
    });
  }

  async enrichBasket() {
    return this.request<{
      enriched: any[];
      enriched_count: number;
      skipped_duplicates: number;
      credits_used: number;
    }>('/api/basket/enrich', {
      method: 'POST',
    });
  }

  // Team Leads
  async getTeamLeads(filter?: 'available' | 'contacted') {
    const params = filter ? `?filter=${filter}` : '';
    return this.request<{ leads: any[]; stats: any }>(`/api/team-leads${params}`);
  }

  // Email (PM only)
  async getTemplates() {
    return this.request<{ templates: any[] }>('/api/email/templates');
  }

  async saveTemplate(template: {
    name: string;
    subject: string;
    body_html: string;
    body_text?: string;
    template_id?: number;
  }) {
    return this.request<{ template_id: number; success: boolean }>('/api/email/templates', {
      method: 'POST',
      body: JSON.stringify(template),
    });
  }

  async deleteTemplate(templateId: number) {
    return this.request<{ success: boolean }>(`/api/email/templates/${templateId}`, {
      method: 'DELETE',
    });
  }

  async getCampaigns() {
    return this.request<{ campaigns: any[]; stats: any }>('/api/email/campaigns');
  }

  async createCampaign(campaign: {
    name: string;
    template_id: number;
    sender_email: string;
    sender_name: string;
    lead_ids: string[];
  }) {
    return this.request<{
      campaign_id: number;
      sent_count: number;
      failed_count: number;
      success: boolean;
    }>('/api/email/campaigns', {
      method: 'POST',
      body: JSON.stringify(campaign),
    });
  }

  async previewEmail(templateId: number, leadId: string) {
    return this.request<{ subject: string; body: string }>(
      `/api/email/preview/${templateId}/${leadId}`
    );
  }

  async sendCampaign(campaign: {
    name: string;
    template_id: number;
    sender_email: string;
    sender_name: string;
    lead_ids: string[];
  }) {
    return this.request<{
      campaign_id: number;
      sent_count: number;
      failed_count: number;
      success: boolean;
    }>('/api/email/send', {
      method: 'POST',
      body: JSON.stringify(campaign),
    });
  }

  async getCampaignStats() {
    return this.request<{
      total_sent: number;
      total_delivered: number;
      open_rate: number;
      click_rate: number;
      by_campaign: any[];
    }>('/api/email/stats');
  }

  // Settings
  async getSettings() {
    return this.request<{ has_apollo_key: boolean; has_sendgrid_key: boolean }>(
      '/api/settings'
    );
  }

  async saveApolloKey(apiKey: string) {
    return this.request<{ success: boolean }>('/api/settings/apollo-key', {
      method: 'POST',
      body: JSON.stringify({ api_key: apiKey }),
    });
  }

  async saveSendgridKey(apiKey: string) {
    return this.request<{ success: boolean }>('/api/settings/sendgrid-key', {
      method: 'POST',
      body: JSON.stringify({ api_key: apiKey }),
    });
  }

  // Admin
  async getAdminStats() {
    return this.request<{ total_credits: number; total_leads: number; total_enriched: number }>(
      '/api/admin/stats'
    );
  }

  async getAdminAnalytics() {
    return this.request<{
      total_users: number;
      total_teams: number;
      total_leads: number;
      total_credits_used: number;
      top_users: any[];
      top_teams: any[];
    }>('/api/admin/analytics');
  }

  async getUsers() {
    return this.request<{ users: any[] }>('/api/admin/users');
  }

  async updateUser(
    email: string,
    data: { role?: string; is_admin?: boolean; membership?: string; blacklist_exempt?: boolean }
  ) {
    return this.request<{ success: boolean }>(`/api/admin/users/${encodeURIComponent(email)}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async saveUser(user: {
    email: string;
    name: string;
    team_name: string;
    role: string;
    is_admin: boolean;
    membership?: string;
    blacklist_exempt?: boolean;
  }) {
    return this.request<{ success: boolean }>('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify(user),
    });
  }

  async getTeams() {
    return this.request<{ teams: any[] }>('/api/admin/teams');
  }

  async addTeamCredits(teamName: string, amount: number) {
    return this.request<{ success: boolean; new_total: number }>(
      `/api/admin/teams/${encodeURIComponent(teamName)}/credits`,
      {
        method: 'POST',
        body: JSON.stringify({ amount }),
      }
    );
  }

  async getBlacklist() {
    return this.request<{ domains: string[] }>('/api/admin/blacklist');
  }

  async addToBlacklist(domain: string) {
    return this.request<{ success: boolean }>(`/api/admin/blacklist/${domain}`, {
      method: 'POST',
    });
  }

  async removeFromBlacklist(domain: string) {
    return this.request<{ success: boolean }>(`/api/admin/blacklist/${domain}`, {
      method: 'DELETE',
    });
  }

  async getAuditLogs() {
    return this.request<{ logs: any[] }>('/api/admin/audit-logs');
  }
}

export const api = new ApiClient();
