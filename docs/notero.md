# Notion mirror (Notero plugin)

**Division of labour**: Zotero owns metadata, PDFs, tags and reading status; the Notero plugin pushes the items of the
watched collections to one Notion database, one way; notes are written in the Notion page body only. Anything Notero
manages (title, Tags, URL, Collections) is overwritten on the next sync — **edit it in Zotero**.

## Zotero side

- Zotero 10.0.x with Notero 2.1.0 (install the same xpi on every machine and connect it to the same Notion database;
  Notero preferences are per client).
- Preferences: watched collections `Dex-Manipulation`, `Humanoid`, `AI Foundation` (not `Evolution Algorithm`);
  "Sync when items are modified" on; "Sync notes" **off**; Notion page title = **Item Short Title**.
- A synced item gets a bare `notion` tag and a link attachment titled `Notion` (link mode 3, pointing at the page).
  Both are Notero's keys — **never delete them**. `notion` is in `keep_bare_tags` in `taxonomy.toml`; the attachment is
  not a PDF, so it never shows up in the dump's `pdfs`.
- Trigger: an item entering a watched collection, or any modification (including edits made through the Web API and
  synced down) is pushed about two seconds later; a URL changed through the API shows up in Notion within a minute.
  Items that were already in a collection before the plugin was installed and untouched since are **not** pushed
  automatically: right-click the collection > *Sync Items to Notion*. Deleting an item or removing it from the
  collection does **not** delete the Notion page.
- Page title = Zotero **Short Title** (nickname > the name before the colon > the title); change it in Zotero.
- URL column = Zotero **URL** field = project page (arXiv / DOI link only when there is no project page). The arXiv
  id lives in the DOI field, so nothing is lost.

## Notion side

```
Paper Reading                      (page)
└── Zotero Papers                  (inline database; Notero's only target; three table views — Dex-Manipulation |
                                    Humanoid | AI Foundation — each filtered on Collections contains <name>)
```

Properties (**name and type must match exactly, case-sensitive; renaming a property silently stops Notero from
filling it** — custom property names are not supported, Notero issue #355; properties Notero doesn't know are left alone):

| Property | Type | Content |
|---|---|---|
| `Name` | Title | Zotero Short Title |
| `Collections` | Multi-select | Zotero collection names; used only for the view filters, hidden in the views |
| `Tags` | Multi-select | all Zotero tags; colored per family (Notero never changes colors; a new value appears in a random color, recolor it once). A value nobody uses yet (e.g. `status:read`) can be created and colored in advance — Notero matches by name |
| `URL` | URL | Zotero URL field = project page. On 2026-09-14 this column had been renamed to `Project URL` and 78 of 81 rows were empty because of it; renamed back |
| `Zotero URI` | URL | opens the item in the zotero.org web library |

Other properties Notero understands (`DOI`, `Year`, `Authors`, `Abstract`, `Publication`, ... 25 in total) can be added
under their exact names, then right-click the collection > *Sync Items to Notion* to back-fill.

## Day to day

1. `zl.py add` (the download skill) -> item lands in a Zotero collection -> a Notion row appears seconds later (short title, project URL, tags).
2. Notes go into the Notion page body.
3. Display name -> Zotero Short Title; link -> Zotero URL; tags / collection / status -> Zotero. Don't edit those four
   columns in Notion.
4. Jump: double-click the `Notion` attachment under a Zotero item (opens the page, "open in app" available); click
   `Zotero URI` in Notion for the web library. The project page is the URL field in Zotero's item pane (the arrow
   button next to it opens it; the reader's Info pane has it too).
5. A column stays empty -> check whether its name was changed. After fixing the name, right-click each watched
   collection > *Sync Items to Notion* to back-fill (Notero only pushes on item changes).
6. Deleted a Notion page and want it back: delete the item's `Notion` attachment, then right-click the item > *Sync to Notion*.
