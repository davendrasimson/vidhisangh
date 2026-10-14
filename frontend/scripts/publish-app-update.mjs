// Publish the current screens to the Android / iOS apps without a store update.
// See src/app/core/platform/live-update.ts for how the apps pick them up.
//
//   node scripts/publish-app-update.mjs                 (from frontend/; Android)
//   node scripts/publish-app-update.mjs --platform ios
//   node scripts/publish-app-update.mjs --dry-run       (build and list, upload nothing)
//
// A release targets the native build in the project (android versionCode or iOS
// CURRENT_PROJECT_VERSION): only phones running exactly that store build take it.
// Only for changes to screens, text and styles. Anything that changes native code
// (a new or upgraded Capacitor plugin, permissions, icons) needs a store update.
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { copyFileSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative } from 'node:path';

const ROOT = new URL('..', import.meta.url).pathname;
const HOST = process.env.VS_DEPLOY_HOST || 'vidhisangh';
const REMOTE = '/opt/vidhisangh/frontend/dist/vidhisangh/browser/app-updates';
const OUT = join(ROOT, 'dist-mobile/vidhisangh/browser');

const args = process.argv.slice(2);
const platform = args.includes('--platform') ? args[args.indexOf('--platform') + 1] : 'android';
const dryRun = args.includes('--dry-run');
if (!['android', 'ios'].includes(platform)) throw new Error('--platform must be android or ios');

function nativeBuild() {
  if (platform === 'android') {
    const gradle = readFileSync(join(ROOT, 'android/app/build.gradle'), 'utf8');
    return { build: gradle.match(/versionCode (\d+)/)[1], name: gradle.match(/versionName "([^"]+)"/)[1] };
  }
  const pbx = readFileSync(join(ROOT, 'ios/App/App.xcodeproj/project.pbxproj'), 'utf8');
  return { build: pbx.match(/CURRENT_PROJECT_VERSION = (\d+);/)[1], name: pbx.match(/MARKETING_VERSION = ([^;]+);/)[1] };
}

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}

const sh = (cmd, cmdArgs, opts = {}) => execFileSync(cmd, cmdArgs, { stdio: ['ignore', 'pipe', 'inherit'], ...opts }).toString();

const { build, name } = nativeBuild();
console.log(`Building the app screens for ${platform} build ${build} (${name})…`);
execFileSync('npx', ['ng', 'build', '--configuration', 'production,mobile'], { cwd: ROOT, stdio: 'inherit' });

const stamp = new Date().toISOString().replace(/[-:]/g, '').slice(0, 13).replace('T', '.');
const version = `${name}-web.${stamp}`;
const list = files(OUT).map((path) => ({
  name: relative(OUT, path),
  sha256: createHash('sha256').update(readFileSync(path)).digest('hex'),
  path,
})).sort((a, b) => a.name.localeCompare(b.name));
console.log(`${version}: ${list.length} files`);
if (dryRun) process.exit(0);

// Files are stored by content hash, so unchanged files are never uploaded twice.
const stage = mkdtempSync(join(tmpdir(), 'vs-app-update-'));
for (const f of list) copyFileSync(f.path, join(stage, f.sha256));
sh('ssh', [HOST, `mkdir -p ${REMOTE}/files`]);
// nginx must be able to read them: never carry the private temp-dir mode across.
sh('rsync', ['-rt', '--chmod=D755,F644', '--ignore-existing', `${stage}/`, `${HOST}:${REMOTE}/files/`]);

let manifest = {};
try { manifest = JSON.parse(sh('ssh', [HOST, `cat ${REMOTE}/latest 2>/dev/null || echo '{}'`])); } catch { manifest = {}; }
manifest[platform] ??= {};
manifest[platform][build] = { version, published_at: new Date().toISOString(), files: list.map(({ name, sha256 }) => ({ name, sha256 })) };
const local = join(stage, 'latest');
writeFileSync(local, JSON.stringify(manifest));
// Replace `latest` in one step, so a phone never reads a half-written file.
sh('scp', ['-q', local, `${HOST}:${REMOTE}/latest.new`]);
sh('ssh', [HOST, `chmod 644 ${REMOTE}/latest.new && mv ${REMOTE}/latest.new ${REMOTE}/latest`]);
rmSync(stage, { recursive: true, force: true });
console.log(`Published ${version}. Phones on ${platform} build ${build} switch to it on their next launch after it downloads.`);
