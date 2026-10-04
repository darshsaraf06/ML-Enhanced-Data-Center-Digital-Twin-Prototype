// Hotspot alert overlay: shown while the server holds an open decision.
import { api } from './api.js';
import { esc, el, num, signed, toast } from './util.js';

export class DecisionOverlay {
    constructor(screen) {
        this.screen = screen;
        this.node = null;
        this.decisionId = null;
        this.deadline = null;
        this.timer = null;
        this.busy = false;
    }

    destroy() {
        clearInterval(this.timer);
        this.node?.remove();
        this.node = null;
    }

    update(state) {
        const d = state.decision;
        if (!d || state.status !== 'DECISION') {
            if (this.node) this.destroy();
            this.decisionId = null;
            return;
        }
        if (d.id !== this.decisionId) this.open(d);
        if (d.secondsLeft !== null && d.secondsLeft !== undefined) this.deadline = performance.now() + d.secondsLeft * 1000;
        this.renderCards(d);
    }

    open(d) {
        this.destroy();
        this.decisionId = d.id;
        this.node = el(`<div class="v3-overlay v3-alert-wrap" role="alertdialog" aria-modal="true" aria-labelledby="alertTitle">
            <div class="v3-alert panel-card">
                <div class="flow-kicker">HOTSPOT ALERT, SIMULATION PAUSED</div>
                <h2 id="alertTitle">${esc(d.headline)}</h2>
                <div class="v3-alert-actions">
                    <button class="btn btn-success btn-lg" data-apply-rec disabled>Apply Recommended</button>
                    <button class="btn btn-outline btn-lg" data-snooze title="Dismiss this alert without action and open no new alert for 5 minutes">Snooze 5 min</button>
                </div>
                <p class="v3-muted v3-small" data-rec-note>Simulating the options; the recommended one appears when all are done.</p>
                <p class="v3-muted">Probability of exceeding the ${num(d.limit, 0)} C limit within 15 minutes: ${num(d.probabilityPercent, 0)} %. Racks at risk: ${esc(d.atRisk.join(', '))}.</p>
                <div class="v3-countdown"><div class="v3-countdown-bar"><span data-bar></span></div>
                <p><b data-secs>30</b> s. Choose a solution within 30 s, or the best one will be applied automatically.</p></div>
                <p class="v3-hint">Each option is simulated 30 minutes ahead in a cloned twin with today's conditions held constant. Unsafe options keep the forecast peak above the limit and cannot be applied.</p>
                <div class="v3-solutions" data-cards></div>
            </div></div>`);
        document.body.appendChild(this.node);
        this.node.addEventListener('click', e => {
            const btn = e.target.closest('[data-apply]');
            if (btn && !btn.disabled) this.choose(btn.dataset.apply);
            const rec = e.target.closest('[data-apply-rec]');
            if (rec && !rec.disabled) this.choose(rec.dataset.applyRec);
            if (e.target.closest('[data-snooze]')) this.snooze();
        });
        clearInterval(this.timer);
        this.timer = setInterval(() => this.tick(), 200);
    }

    tick() {
        if (!this.node || this.deadline === null) return;
        const left = Math.max(0, (this.deadline - performance.now()) / 1000);
        this.node.querySelector('[data-secs]').textContent = Math.ceil(left);
        this.node.querySelector('[data-bar]').style.width = `${(left / 30) * 100}%`;
    }

    renderCards(d) {
        if (!this.node) return;
        const host = this.node.querySelector('[data-cards]');
        const anySafe = d.candidates.some(c => c.result && c.result.safe);
        if (host.childElementCount !== d.candidates.length) {
            host.innerHTML = d.candidates.map(c => `<div class="v3-solution panel-card" data-card="${c.actionId}">
                <div class="v3-panel-head"><strong>${esc(c.title)}</strong><span data-badges></span></div>
                <p class="v3-muted v3-small">${esc(c.description)}</p>
                <div class="v3-solution-metrics" data-metrics><span class="v3-muted">simulating...</span></div>
                <button class="btn btn-outline" data-apply="${c.actionId}" disabled>Apply</button>
            </div>`).join('');
        }
        d.candidates.forEach(c => {
            const card = host.querySelector(`[data-card="${c.actionId}"]`);
            const r = c.result;
            const badges = [];
            if (r) badges.push(`<span class="badge ${r.safe ? 'badge-emerald' : 'badge-plasma'}">${r.safe ? 'Safe' : 'Unsafe'}</span>`);
            if (c.actionId === d.recommended && d.finished) badges.push('<span class="badge badge-cyan">Recommended</span>');
            const b = card.querySelector('[data-badges]');
            const html = badges.join(' ');
            if (b.innerHTML !== html) b.innerHTML = html;
            card.classList.toggle('recommended', c.actionId === d.recommended && d.finished);
            if (r) {
                const m = card.querySelector('[data-metrics]');
                const text = `<span>Predicted peak <b>${num(r.peakInlet, 1)} C</b></span><span>Energy change <b>${signed(r.energyChangePercent, 1)} %</b></span><span>Cost score <b>${num(r.costScore, 2)}</b></span><span>Disruption <b>${num(c.disruption, 2)}</b></span>`;
                if (m.innerHTML !== text) m.innerHTML = text;
            }
            const btn = card.querySelector('[data-apply]');
            btn.disabled = this.busy || !r || (!r.safe && anySafe);
            btn.title = r && !r.safe && anySafe ? 'Unsafe: the forecast peak stays above the limit' : '';
        });
        const rec = this.node.querySelector('[data-apply-rec]');
        rec.disabled = this.busy || !d.finished || !d.recommended;
        rec.dataset.applyRec = d.recommended || '';
        const recCand = d.candidates.find(c => c.actionId === d.recommended);
        rec.textContent = d.finished && recCand ? `Apply Recommended: ${recCand.title}` : 'Apply Recommended';
        const note = this.node.querySelector('[data-rec-note]');
        const done = d.candidates.filter(c => c.result).length;
        note.textContent = d.finished
            ? (recCand && recCand.result.safe ? `Recommended because it is safe with the lowest cost score (${num(recCand.result.costScore, 2)}).`
                : 'No option keeps the racks within the limit; the option with the lowest forecast peak is recommended.')
            : `Simulating the options: ${done} of ${d.candidates.length} done.`;
        this.node.querySelector('[data-snooze]').disabled = this.busy;
    }

    async snooze() {
        if (this.busy) return;
        this.busy = true;
        try {
            await api.snooze();
            toast('Alert dismissed with no action. No new hotspot alert will open for 5 minutes.', 'ok');
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            this.busy = false;
        }
    }

    async choose(actionId) {
        if (this.busy) return;
        this.busy = true;
        try {
            await api.decide(actionId);
            toast('Solution applied. The simulation continues.', 'ok');
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            this.busy = false;
        }
    }
}
