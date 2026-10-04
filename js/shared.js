// Helpers shared by every screen (kept separate from app.js to avoid import cycles).
import { api } from './api.js';

let catalog = null;

export async function getCatalog() {
    if (!catalog) catalog = await api.catalog();
    return catalog;
}

const SUN = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle cx="12" cy="12" r="4.5" fill="currentColor"/><g stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/></g></svg>';
const MOON = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M20.5 14.6A8.5 8.5 0 0 1 9.4 3.5a8.5 8.5 0 1 0 11.1 11.1z"/></svg>';

export function themeIcon() {
    return document.documentElement.getAttribute('data-theme') === 'light' ? SUN : MOON;
}

export function themeToggleHtml() {
    return `<button class="btn-theme-toggle v3-theme" data-theme-toggle title="Switch between light and dark mode" aria-label="Switch between light and dark mode"><span class="theme-icon">${themeIcon()}</span></button>`;
}

export function navigate(hash) {
    if (location.hash === hash) window.dispatchEvent(new HashChangeEvent('hashchange'));
    else location.hash = hash;
}
