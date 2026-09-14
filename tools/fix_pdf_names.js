// Run in Zotero: Tools > Developer > Run JavaScript. One-off repair of attachment file names that picked up the title
// prefix ("[date] [venue] ...") through Zotero's automatic renaming.
// Prerequisite: the file-name template from CLAUDE.md (a library-synced setting, set once on any device).
// Only touches file names containing " - [" (i.e. polluted by the prefix); leaves hand-named files alone.
// Run with DRY = true first to see the list, then set it to false. Zotero syncs the renames to other devices.
var DRY = true;
var items = await Zotero.Items.getAll(Zotero.Libraries.userLibraryID, false, true);
var out = [];
for (let it of items) {
  if (!it.isRegularItem()) continue;
  let att = await it.getBestAttachment();
  if (!att || !att.isStoredFileAttachment()) continue;
  let fn = att.attachmentFilename;
  if (!/ - \[/.test(fn)) continue;
  let base = Zotero.Attachments.getFileBaseNameFromItem(it, { attachmentTitle: att.getField('title') });
  let newName = base + '.' + fn.replace(/^.*\./, '');
  if (newName === fn) continue;
  let r = DRY ? 'DRY' : await att.renameAttachmentFile(newName, { updateTitle: true });
  out.push(r + ' | ' + fn + '  ->  ' + newName);
}
return out.length + ' files\n' + out.join('\n');
