/* Duplicate protection and two-frame confirmation; also executable in Node tests. */
class CaptureGate {
  constructor() { this.reset(); }
  reset() { this.pending = null; this.seen = 0; this.lastSaved = null; this.armed = true; this.blanks = 0; }
  key(value) { return Number(String(value).replace(',', '.')).toFixed(4); }
  saved(value) { this.lastSaved = this.key(value); this.armed = false; this.pending = null; this.seen = 0; this.blanks = 0; }
  observe(value, genuinelyBlank = false) {
    if (value === null || value === undefined) {
      this.pending = null; this.seen = 0;
      this.blanks = genuinelyBlank ? this.blanks + 1 : 0;
      if (this.blanks >= 3) this.armed = true;
      return 'searching';
    }
    const key = this.key(value);
    this.blanks = 0;
    if (!this.armed && key === this.lastSaved) {
      this.pending = null; this.seen = 0;
      return 'duplicate';
    }
    if (key !== this.pending) { this.pending = key; this.seen = 1; return 'confirming'; }
    this.seen += 1;
    return this.seen >= 2 ? 'save' : 'confirming';
  }
}
if (typeof module !== 'undefined') module.exports = CaptureGate;
