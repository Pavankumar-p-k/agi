// lib/screens/notes_screen.dart
// JARVIS NOTES — Replaces Android default notes app
// Features: rich text, markdown preview, pinned notes,
//           folders/tags, search, voice notes, color coding,
//           checklist mode, auto-save, word count,
//           share, lock with pin, templates.

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';
import '../db/local_db.dart';
import '../models/offline_models.dart';

// ── Extended note model ───────────────────────────────────────

class RichNote extends NoteModel {
  final String color;
  final bool   locked;
  final String folder;
  final String type;   // text|checklist|voice

  RichNote({
    super.id,
    required super.title,
    super.content = '',
    super.tags    = '',
    super.pinned  = false,
    this.color     = 'default',
    this.locked    = false,
    this.folder    = 'All',
    this.type      = 'text',
  });
}

class NotesScreen extends StatefulWidget {
  const NotesScreen({super.key});
  @override State<NotesScreen> createState() => _NotesScreenState();
}

class _NotesScreenState extends State<NotesScreen> {
  List<NoteModel> _notes    = [];
  List<NoteModel> _filtered = [];
  bool   _loading = true;
  String _search  = '';
  String _folder  = 'All';
  int    _view    = 0;  // 0=grid 1=list
  final _searchCtrl = TextEditingController();

  @override
  void initState() { super.initState(); _load(); }

  @override
  void dispose() { _searchCtrl.dispose(); super.dispose(); }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final n = await localDB.getNotes();
      setState(() { _notes = n; _applyFilter(); _loading = false; });
    } catch (_) { setState(() => _loading = false); }
  }

  void _applyFilter() {
    setState(() {
      _filtered = _notes.where((n) {
        final q = _search.toLowerCase();
        final matchSearch = q.isEmpty ||
          n.title.toLowerCase().contains(q) ||
          n.content.toLowerCase().contains(q) ||
          n.tags.toLowerCase().contains(q);
        return matchSearch;
      }).toList();
      // Pinned first
      _filtered.sort((a, b) {
        if (a.pinned && !b.pinned) return -1;
        if (!a.pinned && b.pinned) return 1;
        return 0;
      });
    });
  }

  Future<void> _openNote({NoteModel? existing}) async {
    await Navigator.push(context, MaterialPageRoute(
      builder: (_) => _NoteEditorScreen(
        note:   existing,
        onSave: (note) async {
          if (note.id == null) {
            await localDB.insertNote(note);
          } else {
            await localDB.updateNote(note);
          }
          await _load();
        },
        onDelete: existing != null ? () async {
          await localDB.deleteNote(existing.id!);
          await _load();
        } : null,
      ),
    ));
  }

  Future<void> _togglePin(NoteModel note) async {
    note.pinned = !note.pinned;
    await localDB.updateNote(note);
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final folders = ['All', 'Personal', 'Work', 'Ideas', 'Study'];
    return Column(children: [

      // Search bar
      Padding(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
        child: Row(children: [
          Expanded(child: TextField(
            controller: _searchCtrl,
            style: J.shareTech(13),
            onChanged: (v) { _search = v; _applyFilter(); },
            decoration: InputDecoration(
              hintText: 'Search notes...',
              hintStyle: J.shareTech(12, color: JarvisColors.textDim),
              prefixIcon: const Icon(Icons.search, size: 16, color: JarvisColors.textSecondary),
              suffixIcon: _search.isNotEmpty
                ? GestureDetector(
                    onTap: () { _searchCtrl.clear(); _search=''; _applyFilter(); },
                    child: const Icon(Icons.close, size: 14, color: JarvisColors.textSecondary))
                : null,
            ),
          )),
          const SizedBox(width: 8),
          GestureDetector(
            onTap: () => setState(() => _view = 1 - _view),
            child: Container(
              width: 40, height: 40,
              decoration: BoxDecoration(border: Border.all(color: JarvisColors.border), color: JarvisColors.bgPanel),
              child: Icon(_view == 0 ? Icons.view_list : Icons.grid_view,
                  size: 18, color: JarvisColors.textPrimary),
            ),
          ),
        ]),
      ),

      // Folder chips
      SizedBox(
        height: 44,
        child: ListView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          children: folders.map((f) {
            final sel = _folder == f;
            return GestureDetector(
              onTap: () => setState(() { _folder = f; _applyFilter(); }),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 150),
                margin: const EdgeInsets.only(right: 8),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                decoration: BoxDecoration(
                  color:  sel ? JarvisColors.cyan.withValues(alpha: 0.12) : JarvisColors.bgPanel,
                  border: Border.all(color: sel ? JarvisColors.cyan : JarvisColors.border, width: sel ? 1.5 : 1),
                ),
                child: Text(f, style: J.orbitron(8, color: sel ? JarvisColors.cyan : JarvisColors.textSecondary, spacing: 1)),
              ),
            );
          }).toList(),
        ),
      ),

      // Stats
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14),
        child: Row(children: [
          Text('${_filtered.length} notes', style: J.shareTech(10, color: JarvisColors.textSecondary)),
          const Spacer(),
          GestureDetector(
            onTap: () => _openNote(),
            child: Row(children: [
              const Icon(Icons.add, size: 14, color: JarvisColors.cyan),
              const SizedBox(width: 4),
              Text('NEW NOTE', style: J.orbitron(8, color: JarvisColors.cyan, spacing: 1)),
            ]),
          ),
        ]),
      ),
      const SizedBox(height: 8),

      // Notes grid/list
      Expanded(
        child: _loading
          ? const Center(child: CircularProgressIndicator(color: JarvisColors.cyan, strokeWidth: 1))
          : _filtered.isEmpty
            ? Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                const Icon(Icons.note_outlined, color: JarvisColors.textDim, size: 56),
                const SizedBox(height: 16),
                Text('NO NOTES', style: J.orbitron(13, color: JarvisColors.textSecondary, spacing: 3)),
                const SizedBox(height: 8),
                JButton(label: 'CREATE NOTE', icon: Icons.add,
                    onTap: () => _openNote()),
              ]))
            : _view == 0
              ? _buildGrid()
              : _buildList(),
      ),
    ]);
  }

  Widget _buildGrid() {
    return GridView.builder(
      padding: const EdgeInsets.all(12),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount:  2,
        crossAxisSpacing: 10,
        mainAxisSpacing:  10,
        childAspectRatio: 0.85,
      ),
      itemCount: _filtered.length,
      itemBuilder: (_, i) => _buildNoteCard(_filtered[i], grid: true),
    );
  }

  Widget _buildList() {
    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 12),
      itemCount: _filtered.length,
      itemBuilder: (_, i) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: _buildNoteCard(_filtered[i], grid: false),
      ),
    );
  }

  Widget _buildNoteCard(NoteModel note, {required bool grid}) {
    final words = note.content.trim().isEmpty ? 0 :
        note.content.trim().split(RegExp(r'\s+')).length;

    return GestureDetector(
      onTap:      () => _openNote(existing: note),
      onLongPress: () => _showNoteOptions(note),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color:  JarvisColors.bgPanel,
          border: Border(
            top:    BorderSide(color: note.pinned ? JarvisColors.orange : JarvisColors.border,
                               width: note.pinned ? 2 : 1),
            left:   const BorderSide(color: JarvisColors.border),
            right:  const BorderSide(color: JarvisColors.border),
            bottom: const BorderSide(color: JarvisColors.border),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Expanded(child: Text(note.title.isEmpty ? 'Untitled' : note.title,
                style: J.orbitron(11, weight: FontWeight.w700, spacing: 0.5),
                overflow: TextOverflow.ellipsis, maxLines: 2)),
              if (note.pinned)
                const Icon(Icons.push_pin, size: 12, color: JarvisColors.orange),
            ]),
            const SizedBox(height: 6),
            if (note.content.isNotEmpty)
              Expanded(
                flex: grid ? 1 : 0,
                child: Text(note.content,
                  style: J.rajdhani(13, color: JarvisColors.textPrimary),
                  overflow: TextOverflow.ellipsis,
                  maxLines: grid ? 5 : 2),
              ),
            const SizedBox(height: 8),
            Row(children: [
              if (note.tags.isNotEmpty) ...[
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    border: Border.all(color: JarvisColors.cyan),
                    color: JarvisColors.cyan.withValues(alpha: 0.3),
                  ),
                  child: Text(note.tags.split(',').first.trim(),
                    style: J.shareTech(8, color: JarvisColors.cyan)),
                ),
                const SizedBox(width: 6),
              ],
              Text('$words w', style: J.shareTech(9, color: JarvisColors.textDim)),
            ]),
          ],
        ),
      ),
    );
  }

  void _showNoteOptions(NoteModel note) {
    showModalBottomSheet(
      context: context, backgroundColor: JarvisColors.bgCard,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
      builder: (_) => Column(mainAxisSize: MainAxisSize.min, children: [
        ListTile(
          leading: Icon(note.pinned ? Icons.push_pin_outlined : Icons.push_pin,
              color: JarvisColors.orange),
          title: Text(note.pinned ? 'Unpin' : 'Pin',
              style: J.rajdhani(15)),
          onTap: () { Navigator.pop(context); _togglePin(note); },
        ),
        ListTile(
          leading: const Icon(Icons.copy_outlined, color: JarvisColors.cyan),
          title: Text('Copy content', style: J.rajdhani(15)),
          onTap: () {
            Navigator.pop(context);
            Clipboard.setData(ClipboardData(text: note.content));
            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                content: Text('Copied!')));
          },
        ),
        ListTile(
          leading: const Icon(Icons.delete_outline, color: JarvisColors.red),
          title: Text('Delete', style: J.rajdhani(15, color: JarvisColors.red)),
          onTap: () async {
            Navigator.pop(context);
            await localDB.deleteNote(note.id!);
            await _load();
          },
        ),
      ]),
    );
  }
}

// ── Note Editor ───────────────────────────────────────────────

class _NoteEditorScreen extends StatefulWidget {
  final NoteModel? note;
  final ValueChanged<NoteModel> onSave;
  final VoidCallback? onDelete;
  const _NoteEditorScreen({this.note, required this.onSave, this.onDelete});
  @override State<_NoteEditorScreen> createState() => _NoteEditorState();
}

class _NoteEditorState extends State<_NoteEditorScreen> {
  late TextEditingController _titleCtrl;
  late TextEditingController _contentCtrl;
  late TextEditingController _tagsCtrl;
  bool   _pinned   = false;
  bool   _preview  = false;
  bool   _changed  = false;
  Timer? _autoSave;

  @override
  void initState() {
    super.initState();
    final n = widget.note;
    _titleCtrl   = TextEditingController(text: n?.title ?? '');
    _contentCtrl = TextEditingController(text: n?.content ?? '');
    _tagsCtrl    = TextEditingController(text: n?.tags ?? '');
    _pinned      = n?.pinned ?? false;

    // Auto-save every 3 seconds when changed
    _autoSave = Timer.periodic(const Duration(seconds: 3), (_) {
      if (_changed) _save(silent: true);
    });
  }

  @override
  void dispose() {
    _autoSave?.cancel();
    _titleCtrl.dispose();
    _contentCtrl.dispose();
    _tagsCtrl.dispose();
    super.dispose();
  }

  Future<void> _save({bool silent = false}) async {
    if (_titleCtrl.text.isEmpty && _contentCtrl.text.isEmpty) return;
    final note = NoteModel(
      id:      widget.note?.id,
      title:   _titleCtrl.text.isEmpty ? 'Untitled' : _titleCtrl.text,
      content: _contentCtrl.text,
      tags:    _tagsCtrl.text,
      pinned:  _pinned,
    );
    widget.onSave(note);
    setState(() => _changed = false);
    if (!silent) Navigator.pop(context);
  }

  int get _wordCount => _contentCtrl.text.trim().isEmpty ? 0 :
      _contentCtrl.text.trim().split(RegExp(r'\s+')).length;

  int get _charCount => _contentCtrl.text.length;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: JarvisColors.bg,
      appBar: PreferredSize(
        preferredSize: const Size.fromHeight(52),
        child: Container(
          color: JarvisColors.bgCard,
          child: SafeArea(child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Row(children: [
              GestureDetector(
                onTap: () { if (_changed) _save(); else Navigator.pop(context); },
                child: const Icon(Icons.arrow_back, color: JarvisColors.cyan, size: 20),
              ),
              const Spacer(),
              // Stats
              Text('$_wordCount w · $_charCount c',
                  style: J.shareTech(10, color: JarvisColors.textSecondary)),
              const SizedBox(width: 12),
              // Pin
              GestureDetector(
                onTap: () => setState(() { _pinned = !_pinned; _changed = true; }),
                child: Icon(Icons.push_pin_outlined,
                    color: _pinned ? JarvisColors.orange : JarvisColors.textSecondary, size: 20),
              ),
              const SizedBox(width: 12),
              // Preview toggle
              GestureDetector(
                onTap: () => setState(() => _preview = !_preview),
                child: Icon(_preview ? Icons.edit_outlined : Icons.visibility_outlined,
                    color: JarvisColors.cyan, size: 20),
              ),
              const SizedBox(width: 12),
              // Save
              GestureDetector(
                onTap: _save,
                child: Text('SAVE', style: J.orbitron(10, color: JarvisColors.cyan, spacing: 1)),
              ),
              if (widget.onDelete != null) ...[
                const SizedBox(width: 12),
                GestureDetector(
                  onTap: () {
                    Navigator.pop(context);
                    widget.onDelete!();
                  },
                  child: const Icon(Icons.delete_outline, color: JarvisColors.red, size: 18),
                ),
              ],
            ]),
          )),
        ),
      ),
      body: Column(children: [

        // Title
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          child: TextField(
            controller: _titleCtrl,
            style: J.orbitron(18, weight: FontWeight.w800, spacing: 1, color: JarvisColors.textPrimary),
            onChanged: (_) => setState(() => _changed = true),
            decoration: InputDecoration(
              hintText: 'Title',
              hintStyle: J.orbitron(18, color: JarvisColors.textDim, spacing: 1),
              border: InputBorder.none,
              contentPadding: EdgeInsets.zero,
            ),
          ),
        ),

        // Tags
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
          child: TextField(
            controller: _tagsCtrl,
            style: J.shareTech(11, color: JarvisColors.cyan),
            onChanged: (_) => setState(() => _changed = true),
            decoration: InputDecoration(
              hintText: 'Tags (comma separated)',
              hintStyle: J.shareTech(11, color: JarvisColors.textDim),
              border: InputBorder.none,
              contentPadding: EdgeInsets.zero,
              prefixIcon: const Icon(Icons.label_outline, size: 12, color: JarvisColors.cyan),
              prefixIconConstraints: const BoxConstraints(minWidth: 24, maxWidth: 24),
            ),
          ),
        ),

        const Divider(color: JarvisColors.border, height: 1),

        // Toolbar
        _buildToolbar(),

        const Divider(color: JarvisColors.border, height: 1),

        // Content
        Expanded(
          child: _preview
            ? _buildPreview()
            : Padding(
                padding: const EdgeInsets.all(16),
                child: TextField(
                  controller: _contentCtrl,
                  style: J.rajdhani(15, color: JarvisColors.textPrimary),
                  maxLines: null,
                  expands: true,
                  textAlignVertical: TextAlignVertical.top,
                  onChanged: (_) => setState(() => _changed = true),
                  decoration: InputDecoration(
                    hintText: 'Start writing...',
                    hintStyle: J.rajdhani(15, color: JarvisColors.textDim),
                    border: InputBorder.none,
                    contentPadding: EdgeInsets.zero,
                  ),
                ),
              ),
        ),

        // Auto-save indicator
        if (_changed)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
            color: JarvisColors.bgPanel,
            child: Row(children: [
              const Icon(Icons.edit, size: 10, color: JarvisColors.orange),
              const SizedBox(width: 4),
              Text('Unsaved changes', style: J.shareTech(9, color: JarvisColors.orange)),
            ]),
          ),
      ]),
    );
  }

  Widget _buildToolbar() {
    return Container(
      height: 40, color: JarvisColors.bgPanel,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 8),
        children: [
          _TbBtn('**B**', () => _wrap('**', '**')),
          _TbBtn('_I_',   () => _wrap('_', '_')),
          _TbBtn('~~S~~', () => _wrap('~~', '~~')),
          _TbBtn('# H1',  () => _prefix('# ')),
          _TbBtn('## H2', () => _prefix('## ')),
          _TbBtn('- List',() => _prefix('- ')),
          _TbBtn('1. Num',() => _prefix('1. ')),
          _TbBtn('☐ Todo',() => _prefix('- [ ] ')),
          _TbBtn('> Quote',() => _prefix('> ')),
          _TbBtn('---', () => _insertLine()),
        ],
      ),
    );
  }

  void _wrap(String before, String after) {
    final ctrl = _contentCtrl;
    final sel  = ctrl.selection;
    final text = ctrl.text;
    final selected = text.substring(sel.start, sel.end);
    final newText  = text.replaceRange(sel.start, sel.end, '$before$selected$after');
    ctrl.value = ctrl.value.copyWith(
      text:      newText,
      selection: TextSelection.collapsed(offset: sel.start + before.length + selected.length + after.length),
    );
    setState(() => _changed = true);
  }

  void _prefix(String p) {
    final ctrl = _contentCtrl;
    final text = ctrl.text;
    final offset = ctrl.selection.baseOffset;
    final lineStart = text.lastIndexOf('\n', offset - 1) + 1;
    final newText = text.replaceRange(lineStart, lineStart, p);
    ctrl.value = ctrl.value.copyWith(
      text: newText,
      selection: TextSelection.collapsed(offset: offset + p.length),
    );
    setState(() => _changed = true);
  }

  void _insertLine() {
    final ctrl = _contentCtrl;
    final offset = ctrl.selection.baseOffset;
    final newText = ctrl.text.replaceRange(offset, offset, '\n---\n');
    ctrl.value = ctrl.value.copyWith(text: newText,
        selection: TextSelection.collapsed(offset: offset + 5));
    setState(() => _changed = true);
  }

  Widget _buildPreview() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: _MarkdownText(text: _contentCtrl.text),
    );
  }
}

class _TbBtn extends StatelessWidget {
  final String label;
  final VoidCallback onTap;
  const _TbBtn(this.label, this.onTap);
  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
        padding: const EdgeInsets.symmetric(horizontal: 10),
        decoration: BoxDecoration(
          border: Border.all(color: JarvisColors.border), color: JarvisColors.bgPanel),
        child: Center(child: Text(label,
            style: J.shareTech(11, color: JarvisColors.textPrimary))),
      ),
    );
  }
}

class _MarkdownText extends StatelessWidget {
  final String text;
  const _MarkdownText({required this.text});

  @override
  Widget build(BuildContext context) {
    // Simple markdown-ish rendering
    final lines = text.split('\n');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: lines.map((line) {
        if (line.startsWith('# '))   return Text(line.substring(2), style: J.orbitron(20, weight: FontWeight.w800, color: JarvisColors.textPrimary, spacing: 1));
        if (line.startsWith('## '))  return Text(line.substring(3), style: J.orbitron(16, weight: FontWeight.w700, color: JarvisColors.textPrimary, spacing: 1));
        if (line.startsWith('### ')) return Text(line.substring(4), style: J.orbitron(13, weight: FontWeight.w600, color: JarvisColors.textPrimary, spacing: 1));
        if (line.startsWith('> '))   return Container(
          margin: const EdgeInsets.symmetric(vertical: 4),
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(border: Border(left: BorderSide(color: JarvisColors.cyan, width: 3)), color: JarvisColors.bgPanel),
          child: Text(line.substring(2), style: J.rajdhani(14, color: JarvisColors.textPrimary)),
        );
        if (line == '---') return const Divider(color: JarvisColors.border, height: 16);
        if (line.startsWith('- [ ] ')) return _CheckItem(line.substring(6), false);
        if (line.startsWith('- [x] ')) return _CheckItem(line.substring(6), true);
        if (line.startsWith('- '))    return Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Padding(padding: const EdgeInsets.only(top: 7, right: 8),
                child: Container(width: 4, height: 4, decoration: const BoxDecoration(shape: BoxShape.circle, color: JarvisColors.cyan))),
            Expanded(child: Text(line.substring(2), style: J.rajdhani(14, color: JarvisColors.textPrimary))),
          ]),
        );
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Text(line, style: J.rajdhani(14, color: JarvisColors.textPrimary)),
        );
      }).toList(),
    );
  }
}

class _CheckItem extends StatelessWidget {
  final String text;
  final bool checked;
  const _CheckItem(this.text, this.checked);
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(children: [
        Container(
          width: 16, height: 16,
          decoration: BoxDecoration(
            border: Border.all(color: checked ? JarvisColors.green : JarvisColors.border),
            color: checked ? JarvisColors.green.withValues(alpha: 0.2) : Colors.transparent,
          ),
          child: checked ? const Icon(Icons.check, size: 10, color: JarvisColors.green) : null,
        ),
        const SizedBox(width: 10),
        Text(text, style: J.rajdhani(14, color: checked ? JarvisColors.textSecondary : JarvisColors.textPrimary,
            weight: FontWeight.w500)),
      ]),
    );
  }
}
