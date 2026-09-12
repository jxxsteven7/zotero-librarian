// Zotero → 工具 → 开发者 → Run JavaScript 里跑。一次性把被标题前缀"吃"进去的 PDF 文件名改回模板格式。
// 前提：已按 CLAUDE.md §4 设好文件名模板（该模板是库的同步设置，一台机器设好其他设备会跟着）。
// 只动文件名里带 " - [" 的（即被 "[日期] [刊]" 前缀污染的），不碰用户手工命名的（NOA 2023.pdf 之类）。
// 先 DRY=true 看清单，确认后改 false 再跑一次。Zotero 会把改名同步到其他设备（WebDAV 附件也跟着改）。
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
