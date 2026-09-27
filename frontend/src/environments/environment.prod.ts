/** Production environment configuration.
 *  In production the API is same-origin behind the edge proxy (see infra/nginx). */
export const environment = {
  production: true,
  appName: 'VidhiSangh',
  apiBaseUrl: '/api/v1',
  tokenRefreshSkewSeconds: 60,
};
