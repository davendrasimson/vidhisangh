import { Injectable, inject } from '@angular/core';
import { Overlay } from '@angular/cdk/overlay';
import { ComponentPortal } from '@angular/cdk/portal';
import { PhotoViewerComponent } from './photo-viewer.component';

/**
 * Opens the full-screen photo viewer at the top of the page (CDK overlay), so
 * it covers the app's top bar and side navigation whatever screen calls it.
 */
@Injectable({ providedIn: 'root' })
export class PhotoViewerService {
  private readonly overlay = inject(Overlay);

  open(photos: string[], start = 0): void {
    if (!photos.length) return;
    const ref = this.overlay.create({ positionStrategy: this.overlay.position().global(), hasBackdrop: false });
    const viewer = ref.attach(new ComponentPortal(PhotoViewerComponent));
    viewer.setInput('photos', photos);
    viewer.setInput('start', start);
    const sub = viewer.instance.closed.subscribe(() => {
      sub.unsubscribe();
      ref.dispose();
    });
  }
}
