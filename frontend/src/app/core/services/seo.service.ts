import { DOCUMENT } from '@angular/common';
import { Injectable, inject } from '@angular/core';
import { Meta, Title } from '@angular/platform-browser';
import { ActivatedRouteSnapshot, NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs';

/** Search and share tags for a public page, set as route `data: { seo }`. */
export interface SeoData {
  title: string;
  description: string;
}

const SITE = 'https://vidhisangh.com';
const DEFAULT_TITLE = "VidhiSangh — Free professional network for India's legal fraternity";

/**
 * Per-route search tags. Public pages carry `data.seo` and are indexable with
 * their own title, description and canonical URL; every other route (the
 * signed-in app, tokenised client links, auth helpers) is marked `noindex`.
 */
@Injectable({ providedIn: 'root' })
export class SeoService {
  private readonly router = inject(Router);
  private readonly title = inject(Title);
  private readonly meta = inject(Meta);
  private readonly doc = inject(DOCUMENT);

  constructor() {
    this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe(() => this.apply(this.deepest(this.router.routerState.snapshot.root)));
  }

  private deepest(route: ActivatedRouteSnapshot): SeoData | undefined {
    let seo: SeoData | undefined;
    for (let r: ActivatedRouteSnapshot | null = route; r; r = r.firstChild) {
      seo = (r.data['seo'] as SeoData | undefined) ?? seo;
    }
    return seo;
  }

  private apply(seo: SeoData | undefined): void {
    const path = this.router.url.split(/[?#]/)[0];
    if (!seo) {
      this.meta.updateTag({ name: 'robots', content: 'noindex, nofollow' });
      this.setCanonical(null);
      if (!this.title.getTitle()) this.title.setTitle(DEFAULT_TITLE);
      return;
    }
    const url = SITE + (path === '/' ? '/' : path);
    this.title.setTitle(seo.title);
    this.meta.updateTag({ name: 'robots', content: 'index, follow' });
    this.meta.updateTag({ name: 'description', content: seo.description });
    this.meta.updateTag({ property: 'og:title', content: seo.title });
    this.meta.updateTag({ property: 'og:description', content: seo.description });
    this.meta.updateTag({ property: 'og:url', content: url });
    this.meta.updateTag({ name: 'twitter:title', content: seo.title });
    this.meta.updateTag({ name: 'twitter:description', content: seo.description });
    this.setCanonical(url);
  }

  private setCanonical(url: string | null): void {
    let link = this.doc.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!url) {
      link?.remove();
      return;
    }
    if (!link) {
      link = this.doc.createElement('link');
      link.rel = 'canonical';
      this.doc.head.appendChild(link);
    }
    link.href = url;
  }
}
