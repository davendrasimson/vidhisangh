/** Android / iOS app build (Capacitor). The app is served from the device
 *  (https://localhost or capacitor://localhost), so the API and every link meant
 *  for other people must point at the live site explicitly. Use the canonical
 *  host vidhisangh.com: www only proxies plain API calls and has no WebSocket
 *  route. API calls go through Capacitor's native HTTP layer (capacitor.config.ts),
 *  which carries the HttpOnly refresh cookie without browser CORS / SameSite rules. */
export const environment = {
  production: true,
  appName: 'VidhiSangh',
  apiBaseUrl: 'https://vidhisangh.com/api/v1',
  tokenRefreshSkewSeconds: 60,
  publicAppUrl: 'https://vidhisangh.com',
};
