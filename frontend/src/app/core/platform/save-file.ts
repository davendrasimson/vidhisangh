import { isNativeApp } from './platform';

/**
 * Save a file the user asked for.
 *
 * Browser: the usual hidden-anchor download. App: an `<a download>` click does
 * nothing in a WebView, so the file is written to the app's cache and handed to
 * the system share sheet, where the user can open it, save it to Files /
 * Downloads, or send it on (WhatsApp, mail, Drive).
 */
export async function saveBlob(blob: Blob, filename: string): Promise<void> {
  const name = safeFilename(filename);
  if (!isNativeApp()) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return;
  }
  const [{ Filesystem, Directory }, { Share }] = await Promise.all([
    import('@capacitor/filesystem'),
    import('@capacitor/share'),
  ]);
  const written = await Filesystem.writeFile({
    path: `downloads/${name}`,
    data: await blobToBase64(blob),
    directory: Directory.Cache,
    recursive: true,
  });
  try {
    await Share.share({ title: name, files: [written.uri], dialogTitle: name });
  } catch (err) {
    // Closing the share sheet without picking a target is not an error.
    if (!/cancel/i.test(String((err as Error)?.message ?? err))) throw err;
  }
}

/** Keep the name the user sees, minus path separators and control characters. */
export function safeFilename(name: string): string {
  const cleaned = name.replace(/[\\/:*?"<>|\u0000-\u001f]+/g, '_').replace(/^\.+/, '').trim();
  return cleaned.slice(0, 150) || 'download';
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => {
      const result = String(reader.result);
      resolve(result.slice(result.indexOf(',') + 1));
    };
    reader.readAsDataURL(blob);
  });
}
