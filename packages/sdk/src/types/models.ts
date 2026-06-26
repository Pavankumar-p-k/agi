export interface Model {
  id: string;
  name: string;
  provider: string;
  available: boolean;
  description?: string;
  capabilities?: string[];
  context_length?: number;
  cost_per_token?: number;
  speed?: string;
}

export interface ModelListResponse {
  models: Model[];
  total: number;
  default?: string;
}
