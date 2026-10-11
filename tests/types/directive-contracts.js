/** Compile-only directive contract fixtures. */
/** @type {import('../../src/teloce/runtime/directive-contracts.js').CustomDirective<number>} */
const directive = {
  mounted(element, context) {
    context.value.toFixed();
    context.modifiers.includes('extra');
    return { update(next) { next.value.toFixed(); }, destroy() {} };
  },
};
/** @type {import('../../src/teloce/runtime/directive-contracts.js').DirectiveContext<number>} */
const context = {name: 'count', expression: 'count', value: 1, state: {}, modifiers: []};
// @ts-expect-error Numeric directives do not accept string values.
context.value = 'wrong';
// @ts-expect-error Modifiers are strings.
context.modifiers.push(12);
// @ts-expect-error Cleanup is callable.
const invalid = /** @type {import('../../src/teloce/runtime/directive-contracts.js').DirectiveResource<number>} */ ({destroy: 7});
void directive; void invalid;
