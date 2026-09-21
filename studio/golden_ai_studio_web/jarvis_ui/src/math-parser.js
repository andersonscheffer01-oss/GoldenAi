/**
 * Safe Math Expression Parser
 * 
 * REPLACES: brain.js eval()/Function() for calculator commands.
 * 
 * Security: No eval(), no Function(), no dynamic code execution.
 * Supports: +, -, *, /, %, ^, parentheses, sin, cos, tan, sqrt, abs, log, ln, pi, e
 * 
 * Architecture: Tokenize -> Recursive Descent Parse -> Evaluate
 */
(function() {
  'use strict';

  const T = {
    NUM: 'NUM', PLUS: 'PLUS', MINUS: 'MINUS', MUL: 'MUL', DIV: 'DIV',
    MOD: 'MOD', POW: 'POW', LPAREN: 'LPAREN', RPAREN: 'RPAREN',
    FUNC: 'FUNC', COMMA: 'COMMA', EOF: 'EOF'
  };

  const FUNCTIONS = {
    sin: Math.sin, cos: Math.cos, tan: Math.tan,
    asin: Math.asin, acos: Math.acos, atan: Math.atan,
    sqrt: Math.sqrt, abs: Math.abs, log: Math.log10,
    ln: Math.log, log2: Math.log2,
    floor: Math.floor, ceil: Math.ceil, round: Math.round,
    exp: Math.exp, sign: Math.sign,
  };

  const CONSTANTS = { pi: Math.PI, e: Math.E, PI: Math.PI, E: Math.E };

  function tokenize(expr) {
    const tokens = [];
    let i = 0;
    const s = expr.replace(/\s+/g, '');
    while (i < s.length) {
      const c = s[i];
      if (c >= '0' && c <= '9' || c === '.') {
        let num = '';
        while (i < s.length && (s[i] >= '0' && s[i] <= '9' || s[i] === '.')) num += s[i++];
        tokens.push({ type: T.NUM, value: parseFloat(num) });
      } else if (c === '+') { tokens.push({ type: T.PLUS }); i++;
      } else if (c === '-') { tokens.push({ type: T.MINUS }); i++;
      } else if (c === '*') { tokens.push({ type: T.MUL }); i++;
      } else if (c === '/') { tokens.push({ type: T.DIV }); i++;
      } else if (c === '%') { tokens.push({ type: T.MOD }); i++;
      } else if (c === '^') { tokens.push({ type: T.POW }); i++;
      } else if (c === '(') { tokens.push({ type: T.LPAREN }); i++;
      } else if (c === ')') { tokens.push({ type: T.RPAREN }); i++;
      } else if (c === ',') { tokens.push({ type: T.COMMA }); i++;
      } else if (c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z') {
        let name = '';
        while (i < s.length && (s[i] >= 'a' && s[i] <= 'z' || s[i] >= 'A' && s[i] <= 'Z' || s[i] >= '0' && s[i] <= '9')) name += s[i++];
        const lower = name.toLowerCase();
        if (FUNCTIONS[lower]) tokens.push({ type: T.FUNC, value: lower });
        else if (CONSTANTS[name] !== undefined) tokens.push({ type: T.NUM, value: CONSTANTS[name] });
        else throw new Error('Unknown identifier: ' + name);
      } else {
        throw new Error('Unexpected character: ' + c);
      }
    }
    tokens.push({ type: T.EOF });
    return tokens;
  }

  function Parser(tokens) {
    this.tokens = tokens;
    this.pos = 0;
  }
  Parser.prototype.peek = function() { return this.tokens[this.pos]; };
  Parser.prototype.consume = function() { return this.tokens[this.pos++]; };
  Parser.prototype.expect = function(type) {
    const t = this.consume();
    if (t.type !== type) throw new Error('Expected ' + type + ' but got ' + t.type);
    return t;
  };

  Parser.prototype.parse = function() {
    const result = this.parseExpr();
    if (this.peek().type !== T.EOF) throw new Error('Unexpected token after expression');
    return result;
  };

  Parser.prototype.parseExpr = function() {
    let left = this.parseTerm();
    while (this.peek().type === T.PLUS || this.peek().type === T.MINUS) {
      const op = this.consume();
      const right = this.parseTerm();
      left = op.type === T.PLUS ? left + right : left - right;
    }
    return left;
  };

  Parser.prototype.parseTerm = function() {
    let left = this.parsePower();
    while (this.peek().type === T.MUL || this.peek().type === T.DIV || this.peek().type === T.MOD) {
      const op = this.consume();
      const right = this.parsePower();
      if (op.type === T.MUL) left *= right;
      else if (op.type === T.DIV) { if (right === 0) throw new Error('Division by zero'); left /= right; }
      else left %= right;
    }
    return left;
  };

  Parser.prototype.parsePower = function() {
    let base = this.parseUnary();
    if (this.peek().type === T.POW) {
      this.consume();
      const exp = this.parsePower();
      base = Math.pow(base, exp);
    }
    return base;
  };

  Parser.prototype.parseUnary = function() {
    if (this.peek().type === T.MINUS) {
      this.consume();
      return -this.parsePrimary();
    }
    if (this.peek().type === T.PLUS) {
      this.consume();
      return this.parsePrimary();
    }
    return this.parsePrimary();
  };

  Parser.prototype.parsePrimary = function() {
    const t = this.peek();
    if (t.type === T.NUM) { this.consume(); return t.value; }
    if (t.type === T.LPAREN) {
      this.consume();
      const result = this.parseExpr();
      this.expect(T.RPAREN);
      return result;
    }
    if (t.type === T.FUNC) {
      this.consume();
      const fn = FUNCTIONS[t.value];
      this.expect(T.LPAREN);
      const arg = this.parseExpr();
      this.expect(T.RPAREN);
      return fn(arg);
    }
    throw new Error('Unexpected token: ' + t.type);
  };

  function evaluate(expr) {
    if (typeof expr !== 'string' || !expr.trim()) throw new Error('Empty expression');
    if (expr.length > 500) throw new Error('Expression too long');
    const tokens = tokenize(expr);
    const parser = new Parser(tokens);
    const result = parser.parse();
    if (typeof result !== 'number' || !isFinite(result)) throw new Error('Invalid result');
    return result;
  }

  window.MathParser = { evaluate };
})();
