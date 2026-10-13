/** Production environment configuration.
 *  In production the API is same-origin behind the edge proxy (see infra/nginx). */
export const environment = {
  production: true,
  appName: 'VidhiSangh',
  apiBaseUrl: '/api/v1',
  tokenRefreshSkewSeconds: 60,
  /** Origin for links shared outside the app; '' = this page's origin. */
  publicAppUrl: '',
};
