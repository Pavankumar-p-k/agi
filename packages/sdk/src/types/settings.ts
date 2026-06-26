export interface Setting {
  key: string;
  value: unknown;
  default_value: unknown;
  category: string;
  label: string;
  description: string;
  type: 'string' | 'number' | 'boolean' | 'select' | 'json';
  options?: string[];
  restart_required: boolean;
}
