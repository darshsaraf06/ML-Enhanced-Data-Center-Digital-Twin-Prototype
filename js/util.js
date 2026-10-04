// Small shared helpers for the single-page app.

export function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

export function num(value, digits = 1, fallback = 'n/a') {
    return value === null || value === undefined || Number.isNaN(Number(value)) ? fallback : Number(value).toFixed(digits);
}

export function signed(value, digits = 1) {
    if (value === null || value === undefined) return 'n/a';
    const v = Number(value);
    return (v > 0 ? '+' : '') + v.toFixed(digits);
}

export function hms(seconds) {
    const s = Math.max(0, Math.floor(seconds || 0));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return [h, m, sec].map(v => String(v).padStart(2, '0')).join(':');
}

export function hm(seconds) {
    return hms(seconds).slice(0, 5);
}

export function el(html) {
    const t = document.createElement('template');
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
}

export function setText(root, selector, text) {
    const node = root.querySelector(selector);
    if (node && node.textContent !== String(text)) node.textContent = text;
}

// Temperature to color: a continuous scale shared by the heatmap and its legend.
export const TEMP_SCALE = [
    [18, [38, 92, 140]],
    [22, [47, 158, 140]],
    [25, [184, 222, 58]],
    [27, [255, 182, 39]],
    [30, [255, 95, 31]],
    [32, [176, 18, 34]],
];

function scaleRgb(t) {
    const s = TEMP_SCALE;
    if (t <= s[0][0]) return s[0][1];
    for (let i = 1; i < s.length; i++) {
        if (t <= s[i][0]) {
            const [t0, c0] = s[i - 1], [t1, c1] = s[i];
            const k = (t - t0) / (t1 - t0);
            return c0.map((v, j) => Math.round(v + (c1[j] - v) * k));
        }
    }
    return s[s.length - 1][1];
}

export function tempColor(t) {
    return `rgb(${scaleRgb(t).join(',')})`;
}

// Dark or light text, whichever reads better on the temperature color.
export function tempTextColor(t) {
    const [r, g, b] = scaleRgb(t);
    const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
    return lum > 0.55 ? '#14110b' : '#fff8ef';
}

export function toast(text, kind = 'info') {
    const host = document.getElementById('toastHost');
    if (!host) return;
    const node = el(`<div class="v3-toast v3-toast-${kind}" role="status">${esc(text)}</div>`);
    host.appendChild(node);
    setTimeout(() => node.classList.add('show'), 10);
    setTimeout(() => { node.classList.remove('show'); setTimeout(() => node.remove(), 400); }, 6000);
}

export function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// In-page confirmation dialog (no browser dialogs).
export function confirmDialog(title, text, okLabel = 'Confirm', danger = true) {
    return new Promise(resolve => {
        const node = el(`<div class="v3-overlay" role="dialog" aria-modal="true" aria-label="${esc(title)}">
            <div class="v3-dialog panel-card"><h2>${esc(title)}</h2><p class="v3-muted">${esc(text)}</p>
            <div class="v3-row v3-end"><button class="btn btn-outline btn-lg" data-no>Cancel</button>
            <button class="btn ${danger ? 'btn-danger' : 'btn-primary'} btn-lg" data-yes>${esc(okLabel)}</button></div></div></div>`);
        document.body.appendChild(node);
        node.querySelector('[data-yes]').focus();
        node.addEventListener('click', e => {
            if (e.target.closest('[data-yes]')) { node.remove(); resolve(true); }
            else if (e.target.closest('[data-no]') || e.target === node) { node.remove(); resolve(false); }
        });
    });
}
