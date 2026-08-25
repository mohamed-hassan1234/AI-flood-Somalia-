# Localization architecture

The frontend has a typed English (`en`) and Somali (`so`) message catalog in `src/i18n`. The
provider owns language state, persists the non-sensitive preference under
`somalia-ai-language`, and synchronizes the document `lang` attribute for assistive technology.
Unknown or unsupported stored values safely fall back to English.

Navigation paths are stable identifiers and never derived from translated labels. Interpolation
is limited to named display values such as counts, dates, and boundary versions. API enum values,
source names, administrative names, warning text, and other governed records are not machine
translated or rewritten by the client; localization applies only to interface copy around them.

The global shell and national executive dashboard are the initial bilingual surface. New screens
should add typed catalog keys rather than inline language conditionals. Dates use the active locale
for display while their API timestamps remain unchanged. Component and Playwright tests verify
Somali switching, persistence across reloads, navigation labels, executive copy, and the HTML
language declaration.
