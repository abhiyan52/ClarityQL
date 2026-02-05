export type ApiClientConfig = {
  baseUrl: string;
};

export class ApiClient {
  private baseUrl: string;

  constructor(config: ApiClientConfig) {
    this.baseUrl = config.baseUrl;
  }

  async healthCheck(): Promise<{ status: string }> {
    const response = await fetch(`${this.baseUrl}/healthz`);
    return response.json();
  }
}
