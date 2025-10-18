export interface MunicipalityProfile {
  slug: string;
  name: string;
  default_metadata?: Record<string, string>;
}

export interface AppConfig {
  year: string;
  defaultMunicipalitySlug: string;
  municipalities: MunicipalityProfile[];
}

declare global {
  interface Window {
    __APP_CONFIG__?: AppConfig;
  }
}

export {};
