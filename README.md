# com_quiz

Systém pro tvorbu a správu testů a kvízů.

## Metadata

| Pole | Hodnota |
| :--- | :--- |
| Typ | `component` |
| Verze | `0.1.4` |
| Vendor | `klucon` |
| Extension ID | `klucon/com_quiz` |
| Kategorie | `content` |
| Licence | MIT |
| Core minimum | `0.1.0` |
| Python | `>=3.12` |
| Entry point | `src.components.com_quiz` |
| Admin URL | `/admin/com_quiz` |
| Repository | `https://github.com/klucon/com_quiz` |

## Účel

Kvízy a testy jsou marketplace rozšíření pro KLUCON CMS. Balíček je určený pro instalaci přes `/admin/marketplace` a musí projít validací manifestu, checksumu a podpisu.

## Struktura

```text
src/**/com_quiz/
├── manifest.json
├── __init__.py
├── i18n/
└── ...
```

Manifest používá schema `1.0`, deklaruje typ `component`, kompatibilitu s core, i18n doménu `com_quiz`, admin routy, public quiz router a oprávnění.

## Balíčkování

Release ZIP se staví z `src/**/com_quiz/manifest.json` pomocí GitHub Actions workflow `.github/workflows/release-package.yml`. Do balíčku nepatří cache, `.git`, lokální ZIP artefakty ani dočasné soubory.

## Instalace

1. Publikuj ZIP a metadata do marketplace serveru.
2. V CMS otevři `/admin/marketplace`.
3. Vyber `com_quiz` a instaluj verzi `0.1.4`.
4. Po instalaci ověř záznam v příslušné tabulce `installed_*`.

## Poznámky k verzi

Admin sekce je chráněná ACL oprávněním `quiz.manage`.
