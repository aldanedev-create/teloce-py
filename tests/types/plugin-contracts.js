/** Checked examples of optional plugin APIs. */
import {createForm, required, minLength} from '../../src/teloce/runtime/plugins/forms.js';
import {createI18n} from '../../src/teloce/runtime/plugins/i18n.js';
import {createHead} from '../../src/teloce/runtime/plugins/head.js';
import {createAccessibility} from '../../src/teloce/runtime/plugins/accessibility.js';
const form = createForm({name:''}, {name:[required,minLength(2)]});
form.set('name','Ada');
form.subscribe(()=>{});
// @ts-expect-error Validator returns a message, not a number.
createForm({name:''}, {name:[()=>42]});
// @ts-expect-error Submission handler must return a promise.
form.submit(()=>42);
const i18n = createI18n({locale:'en',messages:{en:{hello:'Hi {name}'}}});
i18n.t('hello',{name:'Ada'});
// @ts-expect-error Translation values are strings or plural dictionaries.
createI18n({messages:{en:{hello:42}}});
// @ts-expect-error Titles are text.
createHead({title:42});
// @ts-expect-error Native dialog API requires a dialog element.
createAccessibility().openDialog(document.createElement('div'));
