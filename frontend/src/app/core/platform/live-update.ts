/**
 * Live screen updates for the Android / iOS app, served from vidhisangh.com.
 *
 * The app ships with its screens built in. `scripts/publish-app-update.mjs`
 * publishes newer screens to /app-updates/: a `latest` file listing, per
 * platform and per native build, the version and the SHA-256 of every file,
 * and the files themselves under /app-updates/files/<sha256>. On each launch the
 * app reads `latest`; if its native build has a newer version, the plugin fetches
 * only the files it does not already have (identical files are copied from the
 * built-in screens), verifies every hash, and switches on the next launch.
 *
 * When: only at launch, never while the app is in use. The plugin's own
 * `next()` installs on the next trip to the background, which reloaded the
 * screens while people were in WhatsApp reading a sign-in code (the form was
 * gone when they came back). So a `kill` delay blocks that path on every
 * launch, and a version downloaded earlier is applied with `set()` as soon as
 * the app starts.
 *
 * Safety: each version is built for one native build, so screens never run
 * against native code they were not built with; a store update discards
 * downloaded screens (`resetWhenUpdate`). If new screens fail to start,
 * `notifyAppReady()` is never called and the plugin returns to the previous
 * ones; that version is kept with status "error" and never retried. A version
 * whose download failed is deleted and tried again on the next launch.
 * Any network or server problem just leaves the current screens in place.
 *
 * No Capgo cloud service is used: update checks, stats and channels are switched
 * off in capacitor.config.ts.
 */
import type { CapacitorUpdaterPlugin } from '@capgo/capacitor-updater';

const BASE = 'https://vidhisangh.com/app-updates';
/** The version last switched to, to tell a failed start from a failed download. */
const NEXT_KEY = 'vs_live_update_next';
/** A version downloaded and verified, waiting for the next launch. */
const READY_KEY = 'vs_live_update_ready';

function read(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}

function write(key: string, version: string): void {
  try { localStorage.setItem(key, version); } catch { /* storage unavailable */ }
}

function remembered(): string | null { return read(NEXT_KEY); }

interface PublishedRelease {
  version: string;
  files: { name: string; sha256: string }[];
}

type PublishedManifest = Record<string, Record<string, PublishedRelease>>;

/** Call once at start-up, after the app has rendered. Never throws. */
export async function initLiveUpdates(): Promise<void> {
  try {
    const { CapacitorUpdater } = await import('@capgo/capacitor-updater');
    // These screens started: keep them. Without this the plugin rolls back.
    await CapacitorUpdater.notifyAppReady();
    // Never swap screens when the app goes to the background (see above).
    await CapacitorUpdater.setMultiDelay({ delayConditions: [{ kind: 'kill' }] }).catch(() => undefined);
    if (await applyDownloaded(CapacitorUpdater)) return;
    void checkForUpdate(CapacitorUpdater);
  } catch {
    /* plugin missing (older app build) or not ready: nothing to do */
  }
}

/** The release for this platform and native build, if it is valid. */
export function releaseFor(manifest: unknown, platform: string, build: string): PublishedRelease | null {
  const release = (manifest as PublishedManifest | null)?.[platform]?.[build];
  if (!release || typeof release.version !== 'string' || !release.version || !Array.isArray(release.files) || !release.files.length) {
    return null;
  }
  const valid = release.files.every((f) => typeof f?.name === 'string' && /^[0-9a-f]{64}$/.test(f?.sha256 ?? ''));
  return valid ? release : null;
}

/** At launch: switch to a version downloaded in an earlier session. True if switching. */
async function applyDownloaded(updater: CapacitorUpdaterPlugin): Promise<boolean> {
  try {
    const ready = read(READY_KEY);
    if (!ready) return false;
    const { bundle: current } = await updater.current();
    const { bundles } = await updater.list();
    // A version that failed to start is marked "error" by the plugin: not taken.
    const target = bundles.find((b) => b.version === ready && b.status === 'success');
    if (!target || current.version === ready) return false;
    write(NEXT_KEY, ready);
    await updater.set({ id: target.id });  // reloads into the new screens
    return true;
  } catch {
    return false;
  }
}

async function checkForUpdate(updater: CapacitorUpdaterPlugin): Promise<void> {
  try {
    const [{ App }, { Capacitor }] = await Promise.all([import('@capacitor/app'), import('@capacitor/core')]);
    const { build } = await App.getInfo();
    const response = await fetch(`${BASE}/latest`, { cache: 'no-store' });
    if (!response.ok) return;
    const release = releaseFor(await response.json(), Capacitor.getPlatform(), build);
    if (!release) return;

    const { bundle: current } = await updater.current();
    if (current.version === release.version) return;
    const { bundles } = await updater.list();
    let known = bundles.find((b) => b.version === release.version);
    if (known?.status === 'error') {
      // Switched to once and failed to start: never again; wait for a newer version.
      if (remembered() === release.version) return;
      // Otherwise only the download failed (offline, bad file): clear it and retry.
      await updater.delete({ id: known.id }).catch(() => undefined);
      known = undefined;
    }
    if (known?.status !== 'success' && known?.status !== 'pending') {
      await updater.download({
          url: `${BASE}/files`,
          version: release.version,
          manifest: release.files.map((f) => ({
            file_name: f.name,
            file_hash: f.sha256,
            download_url: `${BASE}/files/${f.sha256}`,
          })),
        });
    }
    // Applied by applyDownloaded() on the next launch.
    write(READY_KEY, release.version);
  } catch {
    /* offline, server unreachable or download failed: keep the current screens */
  }
}
