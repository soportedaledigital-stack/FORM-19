'use strict';
const assert = require('node:assert/strict');
const Gate = require('../static/capture-state.js');
let passed = 0;
function test(name, fn) { fn(); passed += 1; console.log(`OK ${name}`); }
test('Requires two consecutive readings', () => {
 const gate = new Gate(); assert.equal(gate.observe('0,300'), 'confirming'); assert.equal(gate.observe('0,300'), 'save');
});
test('Zero is a valid reading', () => {
 const gate = new Gate(); assert.equal(gate.observe('0,000'), 'confirming'); assert.equal(gate.observe('0,000'), 'save');
});
test('A held display is not duplicated', () => {
 const gate = new Gate(); gate.saved('0,300'); for (let n=0;n<20;n++) assert.equal(gate.observe('0,300'), 'duplicate');
});
test('Equivalent precision does not create a new measurement', () => {
 const gate = new Gate(); gate.saved('0,3'); assert.equal(gate.observe('0,3000'), 'duplicate');
});
test('Ambiguous OCR does not rearm the same display', () => {
 const gate = new Gate(); gate.saved('0,300'); for(let n=0;n<10;n++) gate.observe(null, false); assert.equal(gate.observe('0,300'), 'duplicate');
});
test('Three blank frames allow a repeated measurement', () => {
 const gate = new Gate(); gate.saved('0,300'); for(let n=0;n<3;n++) gate.observe(null, true); assert.equal(gate.observe('0,300'), 'confirming'); assert.equal(gate.observe('0,300'), 'save');
});
test('A changed value needs its own confirmation', () => {
 const gate = new Gate(); gate.saved('0,300'); assert.equal(gate.observe('0,301'), 'confirming'); assert.equal(gate.observe('0,302'), 'confirming'); assert.equal(gate.observe('0,302'), 'save');
});
test('Reset clears old state', () => {
 const gate = new Gate(); gate.saved('0,300'); gate.reset(); assert.equal(gate.observe('0,300'), 'confirming');
});
console.log(`${passed} tests passed.`);
