// lib/screens/file_manager_screen.dart
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_service.dart';
import '../models/models.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';


class FileManagerScreen extends StatefulWidget {
  const FileManagerScreen({super.key});
  @override State<FileManagerScreen> createState() => _FileManagerScreenState();
}

class _FileManagerScreenState extends State<FileManagerScreen> {
  final _api = ApiService();
  String _currentPath = '~';
  List<FileEntry> _entries = [];
  final List<String> _pathHistory = [];
  bool _loading = true;

  @override void initState() { super.initState(); _navigate('~'); }

  Future<void> _navigate(String path) async {
    setState(() => _loading = true);
    try {
      final data = await _api.listFiles(path);
      final entries = _mapEntries(data);
      setState(() {
        _currentPath = (data['path'] as String?) ?? path;
        _entries = entries;
      });
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Cannot open: $e'), backgroundColor: JarvisColors.bgCard),
      );
    }
    setState(() => _loading = false);
  }

  List<FileEntry> _mapEntries(Map<String, dynamic> data) {
    final entries = data['entries'];
    if (entries is List) {
      return entries
          .whereType<Map>()
          .map((j) => FileEntry.fromJson(Map<String, dynamic>.from(j)))
          .toList();
    }

    final files = (data['files'] as List?) ?? const [];
    final dirs = (data['dirs'] as List?) ?? const [];
    final out = <FileEntry>[];

    for (final dir in dirs.whereType<String>()) {
      out.add(FileEntry(
        name: dir,
        isDir: true,
        size: 0,
        modified: DateTime.now(),
      ));
    }
    for (final file in files.whereType<String>()) {
      out.add(FileEntry(
        name: file,
        isDir: false,
        size: 0,
        modified: DateTime.now(),
      ));
    }
    return out;
  }

  void _back() {
    if (_pathHistory.isNotEmpty) {
      _navigate(_pathHistory.removeLast());
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('REMOTE FILES'),
        leading: _pathHistory.isNotEmpty
          ? IconButton(icon: const Icon(Icons.arrow_back, color: JarvisColors.cyan), onPressed: _back)
          : null,
      ),
      body: Column(children: [
        // Path bar
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          color: JarvisColors.bgCard,
          child: Row(children: [
            const Icon(Icons.folder_open_outlined, color: JarvisColors.cyan, size: 14),
            const SizedBox(width: 8),
            Expanded(child: Text(
              _currentPath,
              style: GoogleFonts.shareTech(fontSize: 11, color: JarvisColors.textSecondary),
              overflow: TextOverflow.ellipsis,
            )),
          ]),
        ),
        const Divider(color: JarvisColors.border, height: 1),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          color: JarvisColors.bgPanel,
          child: Text(
            'This screen depends on the backend file API. It does not browse Android storage directly.',
            style: GoogleFonts.shareTech(
              fontSize: 11,
              color: JarvisColors.textSecondary,
            ),
          ),
        ),

        Expanded(child: _loading
          ? const Center(child: CircularProgressIndicator(color: JarvisColors.cyan, strokeWidth: 1.5))
          : _entries.isEmpty
            ? Center(child: Text('EMPTY DIRECTORY', style: GoogleFonts.orbitron(fontSize: 11, letterSpacing: 2, color: JarvisColors.textSecondary)))
            : ListView.builder(
                itemCount: _entries.length,
                itemBuilder: (_, i) {
                  final e = _entries[i];
                  return ListTile(
                    dense: true,
                    leading: Icon(
                      e.isDir ? Icons.folder_outlined : _fileIcon(e.name),
                      color: e.isDir ? JarvisColors.cyan : JarvisColors.textSecondary,
                      size: 20,
                    ),
                    title: Text(e.name, style: GoogleFonts.shareTech(fontSize: 13, color: JarvisColors.textPrimary)),
                    subtitle: Text(
                      e.isDir ? 'Directory' : e.sizeFormatted,
                      style: GoogleFonts.orbitron(fontSize: 9, color: JarvisColors.textSecondary, letterSpacing: 1),
                    ),
                    trailing: Text(
                      _formatDate(e.modified),
                      style: GoogleFonts.shareTech(fontSize: 10, color: JarvisColors.textSecondary),
                    ),
                    onTap: () {
                      if (e.isDir) {
                        _pathHistory.add(_currentPath);
                        _navigate('$_currentPath/${e.name}');
                      }
                    },
                  );
                },
              ),
        ),
      ]),
    );
  }

  IconData _fileIcon(String name) {
    final ext = name.split('.').last.toLowerCase();
    if (['jpg','jpeg','png','gif','webp'].contains(ext)) return Icons.image_outlined;
    if (['mp4','mkv','avi','mov'].contains(ext)) return Icons.movie_outlined;
    if (['mp3','flac','wav','aac'].contains(ext)) return Icons.music_note_outlined;
    if (['pdf'].contains(ext)) return Icons.picture_as_pdf_outlined;
    if (['doc','docx'].contains(ext)) return Icons.description_outlined;
    if (['py','dart','js','ts','java'].contains(ext)) return Icons.code_outlined;
    if (['zip','rar','7z'].contains(ext)) return Icons.archive_outlined;
    return Icons.insert_drive_file_outlined;
  }

  String _formatDate(DateTime d) {
    final now = DateTime.now();
    if (d.year == now.year && d.month == now.month && d.day == now.day) {
      return '${d.hour.toString().padLeft(2,'0')}:${d.minute.toString().padLeft(2,'0')}';
    }
    return '${d.day}/${d.month}/${d.year.toString().substring(2)}';
  }
}
