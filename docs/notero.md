# Optional: mirror the library to Notion with Notero

zotero-librarian ends at Zotero. If you also want the papers as a Notion database — to write reading notes next to
them, or to browse from a phone — the [Notero](https://github.com/dvanoni/notero) plugin does that, one way, and the
conventions this tool enforces happen to be exactly what makes the mirror useful. Nothing in the code depends on
Notero; this page is the recipe.

**Division of labour**: Zotero owns metadata, PDFs, tags and reading status; Notero pushes the items of the watched
collections to one Notion database; notes are written in the Notion page body. Anything Notero manages (title, Tags,
URL, Collections) is overwritten on the next sync — edit it in Zotero.

## Zotero side

- Install the Notero xpi on every machine and connect each to the same Notion database (preferences are per client).
- Preferences: watch the collections you want mirrored; "Sync when items are modified" on; "Sync notes" off;
  Notion page title = **Item Short Title** (the scripts set it to the paper's short name).
- A synced item gets a bare `notion` tag and a link attachment titled `Notion`. Both are Notero's keys: `notion` is
  listed in `keep_bare_tags` in `taxonomy.toml` so the scripts never touch it (and hide it in reports); never delete
  the attachment either.
- What triggers a push: an item entering a watched collection, or any modification — including edits made through
  the Web API once the client has synced them down (a URL set by `zl.py` shows up in Notion within a minute). Items
  that were already in a collection before Notero was installed are not pushed until they change: right-click the
  collection > *Sync Items to Notion*. Deleting an item does not delete its Notion page.

## Notion side

One database, whatever page it lives on; views filtered on `Collections` give one table per collection.
Property **names and types must match Notero's exactly, case-sensitive** — renaming a property silently stops Notero
from filling it (custom names are not supported, Notero issue #355); properties Notero doesn't know are left alone.

| Property | Type | Filled with |
|---|---|---|
| `Name` | Title | Zotero Short Title |
| `Collections` | Multi-select | collection names (for the view filters) |
| `Tags` | Multi-select | all Zotero tags — colour them per family once; Notero matches values by name and never recolours |
| `URL` | URL | Zotero URL field = the project page (arXiv / DOI link only when there is none) |
| `Zotero URI` | URL | opens the item in the zotero.org web library |

Notero knows about 25 more (`DOI`, `Year`, `Authors`, `Abstract`, `Publication`, ...): add any of them under its exact
name, then *Sync Items to Notion* on each watched collection to back-fill.

## Day to day

- `zl.py add` -> item lands in a watched collection -> the Notion row appears seconds later with short title, project
  URL and tags. Write notes in the page body; don't edit the mirrored columns in Notion.
- Jump both ways: double-click the `Notion` attachment under the Zotero item; click `Zotero URI` in Notion.
- A column stays empty -> its name was changed; fix the name, then *Sync Items to Notion* to back-fill.
- Deleted a Notion page by mistake -> delete the item's `Notion` attachment, right-click the item > *Sync to Notion*.
