/** Development environment configuration. */
export const environment = {
  production: false,
  appName: 'VidhiSangh',
  apiBaseUrl: 'http://localhost:8000/api/v1',
  tokenRefreshSkewSeconds: 60,
  /** Origin for links shared outside the app; '' = this page's origin. */
  publicAppUrl: '',
};
