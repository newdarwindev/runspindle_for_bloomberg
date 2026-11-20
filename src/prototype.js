/* Synthetic, in-memory Console prototype for catalog case 10. No external calls. */
(function (root) {
  const BEFORE_SUBMISSION = ['preview', 'approved'];
  const NEEDS_READBACK = ['pending_readback', 'uncertain'];
  const ACTIVE = [...BEFORE_SUBMISSION, ...NEEDS_READBACK];

  function start() {
    return { phase: 'setup', preview: null, previousPhase: null, events: [] };
  }

  function calculate(input) {
    const prior = Number(input.priorClose);
    const current = Number(input.currentClose);
    const dividend = Number(input.dividend);
    if (!input.instrument || !input.priorDate || !input.currentDate ||
        input.priorClose === '' || input.currentClose === '' || input.dividend === '' ||
        input.currentDate <= input.priorDate || !input.observedAt ||
        !Number.isFinite(prior) || prior <= 0 || !Number.isFinite(current) || current < 0 ||
        !Number.isFinite(dividend) || dividend < 0 || !input.freshnessConfirmed ||
        !input.entitlementConfirmed || !input.noOtherActionConfirmed) {
      throw new Error('Complete the exact instrument, dates, source checks, and nonnegative prices.');
    }
    const raw = (current - prior) / prior;
    const adjusted = (current + dividend - prior) / prior;
    return { instrument: input.instrument, priorDate: input.priorDate,
      currentDate: input.currentDate, observedAt: input.observedAt,
      rawReturn: raw, adjustedReturn: adjusted,
      decision: raw < 0 && adjusted > 0 ? 'Pass: reject the raw-price short signal' : 'Pause: example rule does not apply' };
  }

  function transition(state, action, input) {
    const next = { ...state, events: state.events.slice() };
    function requirePhase(...phases) {
      if (!phases.includes(state.phase)) throw new Error(`${action} is unavailable from ${state.phase}.`);
    }
    if (action === 'reset') return start();
    if (action === 'preview') {
      requirePhase('setup');
      next.preview = calculate(input);
      next.phase = next.preview.decision.startsWith('Pass') ? 'preview' : 'paused';
    } else if (action === 'approve') {
      requirePhase('preview'); next.phase = 'approved';
    } else if (action === 'record') {
      requirePhase('approved'); next.phase = 'pending_readback';
    } else if (action === 'simulate_unknown') {
      requirePhase('approved'); next.phase = 'uncertain';
    } else if (action === 'reconcile_found') {
      requirePhase(...NEEDS_READBACK); next.phase = 'recorded';
    } else if (action === 'reconcile_absent') {
      requirePhase(...NEEDS_READBACK); next.phase = 'uncertain';
    } else if (action === 'review') {
      requirePhase('recorded'); next.phase = 'review_pending';
    } else if (action === 'takeover') {
      requirePhase(...ACTIVE); next.previousPhase = state.phase; next.phase = 'takeover';
    } else if (action === 'handback') {
      requirePhase('takeover');
      next.phase = NEEDS_READBACK.includes(state.previousPhase) ? 'uncertain' : 'setup';
      next.previousPhase = null;
      if (next.phase === 'setup') next.preview = null;
    } else if (action === 'pause') {
      requirePhase(...BEFORE_SUBMISSION); next.phase = 'paused';
    } else if (action === 'cancel') {
      requirePhase('setup', ...ACTIVE, 'paused', 'takeover'); next.phase = 'cancelled';
    } else {
      throw new Error(`Unknown action: ${action}`);
    }
    next.events.push(`${action}: ${state.phase} → ${next.phase}`);
    return next;
  }

  const api = { start, calculate, transition };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (!root.document) return;

  const form = root.document.querySelector('#setup');
  if (!form) return;
  const phase = root.document.querySelector('#phase');
  const summary = root.document.querySelector('#summary');
  const history = root.document.querySelector('#history');
  const error = root.document.querySelector('#error');
  let state = start();

  function render() {
    phase.textContent = state.phase.replace('_', ' ').toUpperCase();
    summary.textContent = NEEDS_READBACK.includes(state.phase)
      ? 'The simulated effect requires readback. An inconclusive result keeps this run paused for reconciliation.'
      : state.preview
      ? `${state.preview.decision}. Raw ${(state.preview.rawReturn * 100).toFixed(1)}%; cash-adjusted ${(state.preview.adjustedReturn * 100).toFixed(1)}%. This is a synthetic preview, not independently accepted.`
      : 'Enter the synthetic observation and preview the rule.';
    history.replaceChildren(...state.events.map(text => {
      const item = root.document.createElement('li'); item.textContent = text; return item;
    }));
    form.querySelectorAll('input').forEach(field => { field.disabled = state.phase !== 'setup'; });
    root.document.querySelectorAll('[data-action]').forEach(button => {
      const allowed = {
        preview: ['setup'], approve: ['preview'], record: ['approved'],
        simulate_unknown: ['approved'], reconcile_found: NEEDS_READBACK,
        reconcile_absent: NEEDS_READBACK, review: ['recorded'], takeover: ACTIVE,
        handback: ['takeover'], pause: BEFORE_SUBMISSION,
        cancel: ['setup', ...ACTIVE, 'paused', 'takeover'], reset: ['setup', ...ACTIVE, 'paused', 'takeover', 'cancelled', 'recorded', 'review_pending']
      };
      button.disabled = !allowed[button.dataset.action].includes(state.phase);
    });
  }

  root.document.querySelectorAll('[data-action]').forEach(button => button.addEventListener('click', () => {
    try {
      const fields = Object.fromEntries(new FormData(form));
      fields.freshnessConfirmed = form.elements.freshnessConfirmed.checked;
      fields.entitlementConfirmed = form.elements.entitlementConfirmed.checked;
      fields.noOtherActionConfirmed = form.elements.noOtherActionConfirmed.checked;
      state = transition(state, button.dataset.action, fields);
      error.textContent = '';
    } catch (cause) { error.textContent = cause.message; }
    render();
  }));
  render();
})(typeof window === 'undefined' ? globalThis : window);
