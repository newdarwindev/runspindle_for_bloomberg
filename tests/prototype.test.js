const test = require('node:test');
const assert = require('node:assert/strict');
const { start, calculate, transition } = require('../src/prototype.js');

const input = {
  instrument: 'SYNTH-CASE-10', priorDate: '2026-11-13', currentDate: '2026-11-14',
  observedAt: '2026-11-15T12:00', priorClose: '50.00', currentClose: '48.90',
  dividend: '1.20', freshnessConfirmed: true, entitlementConfirmed: true,
  noOtherActionConfirmed: true
};

test('synthetic calculation gives the supplied Pass decision', () => {
  const result = calculate(input);
  assert.equal(result.rawReturn.toFixed(3), '-0.022');
  assert.equal(result.adjustedReturn.toFixed(3), '0.002');
  assert.match(result.decision, /^Pass/);
  assert.throws(() => calculate({ ...input, noOtherActionConfirmed: false }));
});

test('approval and uncertain effect require readback before review', () => {
  let state = transition(start(), 'preview', input);
  assert.throws(() => transition(state, 'record'));
  state = transition(state, 'approve');
  state = transition(state, 'simulate_unknown');
  assert.equal(state.phase, 'uncertain');
  assert.throws(() => transition(state, 'record'));
  state = transition(state, 'reconcile_found');
  assert.equal(transition(state, 'review').phase, 'review_pending');
});

test('inconclusive readback and handback retain uncertainty', () => {
  let state = transition(transition(start(), 'preview', input), 'approve');
  state = transition(state, 'simulate_unknown');
  state = transition(state, 'reconcile_absent');
  assert.equal(state.phase, 'uncertain');
  assert.throws(() => transition(state, 'approve'));
  assert.throws(() => transition(state, 'record'));
  state = transition(state, 'takeover');
  state = transition(state, 'handback');
  assert.equal(state.phase, 'uncertain');
  assert.throws(() => transition(state, 'record'));
  assert.equal(transition(state, 'reconcile_found').phase, 'recorded');
});

test('simulated record needs readback and pre-submission handback clears the draft', () => {
  const approved = transition(transition(start(), 'preview', input), 'approve');
  const pending = transition(approved, 'record');
  assert.equal(pending.phase, 'pending_readback');
  assert.throws(() => transition(pending, 'review'));
  assert.equal(transition(pending, 'reconcile_found').phase, 'recorded');
  const returned = transition(transition(approved, 'takeover'), 'handback');
  assert.equal(returned.phase, 'setup');
  assert.equal(returned.preview, null);
  assert.throws(() => transition(returned, 'approve'));
});
