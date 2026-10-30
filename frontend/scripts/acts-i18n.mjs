// Hindi for the chrome of the public bare-act and tool pages (header, footer,
// breadcrumbs, buttons). The English text of a `data-i18n` element is the key;
// `/acts/i18n.js` (emitted by build-act-pages.mjs) swaps it when the visitor
// picks हिन्दी, and keeps the choice in localStorage under `vs.lang`, the key
// the app's UiLanguageService uses, so it carries into the app. The Act text
// itself stays English (the official Hindi PDFs are linked where published).
export const ACT_I18N = {
  'Join now': 'अभी जुड़ें',
  'Sign in': 'साइन इन',
  'Bare Acts': 'बेयर एक्ट',
  'Free tools': 'निःशुल्क टूल',
  'Privacy': 'गोपनीयता',
  'Terms': 'शर्तें',
  'VidhiSangh is developed and managed by': 'VidhiSangh का विकास और प्रबंधन',
  'WhatsApp:': 'द्वारा किया जाता है। WhatsApp:',
  'Text reproduced from the official publication for reference. Check the official source and later amendments before relying on it.':
    'पाठ संदर्भ के लिए आधिकारिक प्रकाशन से लिया गया है। इस पर भरोसा करने से पहले आधिकारिक स्रोत और बाद के संशोधन जाँचें।',
  'Share on WhatsApp': 'WhatsApp पर साझा करें',
  'Old law equivalent': 'पुराने कानून में समतुल्य',
  'In the new law': 'नए कानून में',
  'Now in the new law': 'अब नए कानून में',
  'Search by section number or subject': 'धारा संख्या या विषय से खोजें',
  'Calculate the last date': 'अंतिम तिथि निकालें',
  'Calculate': 'गणना करें',
  'Calculate interest': 'ब्याज निकालें',
  'Look up': 'खोजें',
  'Limitation calculator': 'परिसीमा कैलकुलेटर',
  'Default bail calculator': 'डिफ़ॉल्ट बेल कैलकुलेटर',
  'Interest calculator': 'ब्याज कैलकुलेटर',
  'Offence screener': 'अपराध स्क्रीनर',
};

/** The browser-side switcher, served as a file (the site's CSP allows no inline scripts). */
export const I18N_JS = `(function(){var D=${JSON.stringify(ACT_I18N)};var K='vs.lang';var b=document.getElementById('vs-lang');
function apply(l){document.documentElement.lang=l==='hi'?'hi-IN':'en-IN';document.querySelectorAll('[data-i18n]').forEach(function(e){if(e.dataset.en===undefined)e.dataset.en=e.textContent.trim();var t=l==='hi'?D[e.dataset.en]:null;e.textContent=t||e.dataset.en;});if(b){b.textContent=l==='hi'?'English':'हिन्दी';b.setAttribute('lang',l==='hi'?'en':'hi');}}
var l='en';try{l=localStorage.getItem(K)==='hi'?'hi':'en';}catch(e){}apply(l);
if(b)b.addEventListener('click',function(){l=l==='hi'?'en':'hi';try{localStorage.setItem(K,l);}catch(e){}apply(l);});})();
`;
