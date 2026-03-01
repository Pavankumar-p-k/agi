// lib/screens/face_recognition_screen.dart
import 'dart:typed_data';
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:image_picker/image_picker.dart';
import '../services/api_service.dart';
import '../models/models.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class FaceRecognitionScreen extends StatefulWidget {
  const FaceRecognitionScreen({super.key});
  @override State<FaceRecognitionScreen> createState() => _FaceRecognitionScreenState();
}

class _FaceRecognitionScreenState extends State<FaceRecognitionScreen> with SingleTickerProviderStateMixin {
  final _api   = ApiService();
  final _picker = ImagePicker();
  late TabController _tabCtrl;
  List<KnownFace> _faces = [];
  bool _loading = true;
  Map<String, dynamic>? _identifyResult;

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 3, vsync: this);
    _loadFaces();
  }

  @override
  void dispose() { _tabCtrl.dispose(); super.dispose(); }

  Future<void> _loadFaces() async {
    setState(() => _loading = true);
    try { _faces = await _api.getFaces(); } catch (_) {}
    setState(() => _loading = false);
  }

  Future<void> _identify() async {
    final img = await _picker.pickImage(source: ImageSource.gallery, imageQuality: 85);
    if (img == null) return;
    final bytes = await img.readAsBytes();
    setState(() => _identifyResult = null);
    try {
      final result = await _api.identifyFace(bytes);
      setState(() => _identifyResult = result);
    } catch (e) {
      setState(() => _identifyResult = {'status': 'error', 'msg': e.toString()});
    }
  }

  Future<void> _register() async {
    final nameCtrl     = TextEditingController();
    final relationCtrl = TextEditingController();
    final infoCtrl     = TextEditingController();
    final List<Uint8List> images = [];

    await showModalBottomSheet(
      context: context,
      backgroundColor: JarvisColors.bgCard,
      isScrollControlled: true,
      builder: (ctx) => StatefulBuilder(builder: (ctx, setS) =>
        Padding(
          padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
          child: Container(
            padding: const EdgeInsets.all(20),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Text('REGISTER FACE', style: GoogleFonts.orbitron(fontSize: 13, color: JarvisColors.cyan, letterSpacing: 2)),
              const SizedBox(height: 16),
              TextField(controller: nameCtrl, style: GoogleFonts.shareTech(color: JarvisColors.textPrimary), decoration: const InputDecoration(hintText: 'Person Name')),
              const SizedBox(height: 10),
              TextField(controller: relationCtrl, style: GoogleFonts.shareTech(color: JarvisColors.textPrimary), decoration: const InputDecoration(hintText: 'Relation (friend/family/colleague)')),
              const SizedBox(height: 10),
              TextField(controller: infoCtrl, style: GoogleFonts.shareTech(color: JarvisColors.textPrimary), decoration: const InputDecoration(hintText: 'Info to remember about them')),
              const SizedBox(height: 16),
              // Image picker
              GestureDetector(
                onTap: () async {
                  final picked = await _picker.pickMultiImage(imageQuality: 85);
                  for (final img in picked) {
                    final bytes = await img.readAsBytes();
                    setS(() => images.add(bytes));
                  }
                },
                child: Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(border: Border.all(color: JarvisColors.cyan.withOpacity(0.4), style: BorderStyle.solid), color: JarvisColors.bgPanel),
                  child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                    const Icon(Icons.add_photo_alternate_outlined, color: JarvisColors.cyan, size: 18),
                    const SizedBox(width: 8),
                    Text('Add Photos (${images.length} selected)', style: GoogleFonts.orbitron(fontSize: 11, color: JarvisColors.cyan, letterSpacing: 1)),
                  ]),
                ),
              ),
              const SizedBox(height: 16),
              SizedBox(width: double.infinity, child: JButton(
                label: 'REGISTER',
                icon: Icons.save_outlined,
                onTap: () async {
                  if (nameCtrl.text.isEmpty || images.isEmpty) return;
                  await _api.registerFace(
                    name: nameCtrl.text,
                    imageBytesList: images.map((b) => b.toList()).toList(),
                    relation: relationCtrl.text,
                    info: infoCtrl.text,
                  );
                  Navigator.pop(ctx);
                  _loadFaces();
                },
              )),
            ]),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('FACE RECOGNITION'),
        bottom: TabBar(
          controller: _tabCtrl,
          indicatorColor: JarvisColors.cyan,
          labelStyle: GoogleFonts.orbitron(fontSize: 10, letterSpacing: 1.5),
          tabs: const [Tab(text: 'IDENTIFY'), Tab(text: 'DATABASE'), Tab(text: 'REGISTER')],
        ),
      ),
      body: TabBarView(controller: _tabCtrl, children: [
        // ── Identify tab ──
        Padding(padding: const EdgeInsets.all(20), child: Column(children: [
          JPanel(label: 'FACE IDENTIFICATION', child: Column(children: [
            Text('Upload an image to identify the person', style: GoogleFonts.shareTech(fontSize: 13, color: JarvisColors.textSecondary)),
            const SizedBox(height: 16),
            SizedBox(width: double.infinity, child: JButton(label: 'SELECT IMAGE', icon: Icons.image_search_outlined, onTap: _identify)),
          ])),
          if (_identifyResult != null) ...[
            const SizedBox(height: 16),
            JPanel(
              label: 'RESULT',
              borderColor: _identifyResult!['status'] == 'identified' ? JarvisColors.green : JarvisColors.orange,
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Icon(
                    _identifyResult!['status'] == 'identified' ? Icons.check_circle_outline : Icons.help_outline,
                    color: _identifyResult!['status'] == 'identified' ? JarvisColors.green : JarvisColors.orange,
                    size: 18,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    _identifyResult!['status'] == 'identified'
                      ? (_identifyResult!['person_name'] ?? 'Identified')
                      : 'UNKNOWN PERSON',
                    style: GoogleFonts.orbitron(fontSize: 14, color: JarvisColors.textPrimary, fontWeight: FontWeight.w700),
                  ),
                ]),
                if (_identifyResult!['status'] == 'identified') ...[
                  const SizedBox(height: 10),
                  if (_identifyResult!['relation'] != null)
                    Text('Relation: ${_identifyResult!['relation']}', style: GoogleFonts.shareTech(fontSize: 12, color: JarvisColors.textPrimary)),
                  if (_identifyResult!['info'] != null && (_identifyResult!['info'] as String).isNotEmpty)
                    Text('Info: ${_identifyResult!['info']}', style: GoogleFonts.shareTech(fontSize: 12, color: JarvisColors.textSecondary)),
                  Text('Confidence: ${_identifyResult!['confidence']}%',
                    style: GoogleFonts.orbitron(fontSize: 11, color: JarvisColors.green, letterSpacing: 1)),
                ],
              ]),
            ),
          ],
        ])),

        // ── Database tab ──
        _loading
          ? const Center(child: CircularProgressIndicator(color: JarvisColors.cyan, strokeWidth: 1.5))
          : _faces.isEmpty
            ? Center(child: Text('NO FACES REGISTERED', style: GoogleFonts.orbitron(fontSize: 11, letterSpacing: 2, color: JarvisColors.textSecondary)))
            : ListView.builder(
                padding: const EdgeInsets.all(16),
                itemCount: _faces.length,
                itemBuilder: (_, i) {
                  final f = _faces[i];
                  return Padding(padding: const EdgeInsets.only(bottom: 10), child: JPanel(child: Row(children: [
                    Container(
                      width: 44, height: 44,
                      decoration: BoxDecoration(
                        border: Border.all(color: JarvisColors.cyan.withOpacity(0.4)),
                        color: JarvisColors.bgPanel,
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(Icons.face_outlined, color: JarvisColors.cyan, size: 22),
                    ),
                    const SizedBox(width: 14),
                    Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(f.name, style: GoogleFonts.orbitron(fontSize: 13, color: JarvisColors.textPrimary, letterSpacing: 1)),
                      Text('${f.relation.toUpperCase()} · ${f.imageCount} images', style: GoogleFonts.shareTech(fontSize: 11, color: JarvisColors.textSecondary)),
                    ])),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(border: Border.all(color: _accessColor(f.accessLevel).withOpacity(0.4))),
                      child: Text(f.accessLevel.toUpperCase(), style: GoogleFonts.orbitron(fontSize: 8, color: _accessColor(f.accessLevel), letterSpacing: 1)),
                    ),
                  ])));
                },
              ),

        // ── Register tab ──
        Padding(padding: const EdgeInsets.all(20), child: Column(children: [
          JPanel(label: 'REGISTER NEW FACE', child: Column(children: [
            Text('Add a person to JARVIS\'s recognition database. Provide 5+ clear photos for best accuracy.',
              style: GoogleFonts.shareTech(fontSize: 13, color: JarvisColors.textSecondary, height: 1.5)),
            const SizedBox(height: 16),
            SizedBox(width: double.infinity, child: JButton(label: 'START REGISTRATION', icon: Icons.add_circle_outline, onTap: _register)),
          ])),
          const SizedBox(height: 16),
          JPanel(label: 'TIPS', child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              '▸ Use 5–10 different photos',
              '▸ Different angles & lighting',
              '▸ Avoid sunglasses or masks',
              '▸ Clear, high-quality images',
            ].map((t) => Padding(padding: const EdgeInsets.only(bottom: 6), child: Text(t,
              style: GoogleFonts.shareTech(fontSize: 12, color: JarvisColors.textPrimary.withOpacity(0.8))))).toList(),
          )),
        ])),
      ]),
    );
  }

  Color _accessColor(String level) {
    switch (level) {
      case 'owner':   return JarvisColors.cyan;
      case 'trusted': return JarvisColors.green;
      case 'blocked': return JarvisColors.red;
      default:        return JarvisColors.textSecondary;
    }
  }
}


// ════════════════════════════════════════
//  MEDIA PLAYER SCREEN
// ════════════════════════════════════════
class MediaPlayerScreen extends StatefulWidget {
  const MediaPlayerScreen({super.key});
  @override State<MediaPlayerScreen> createState() => _MediaPlayerScreenState();
}

class _MediaPlayerScreenState extends State<MediaPlayerScreen> {
  final _api = ApiService();
  MediaStatus? _status;
  List<Track>  _playlist = [];
  bool _loading = true;

  @override void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    try {
      final results = await Future.wait([_api.getMediaStatus(), _api.getPlaylist()]);
      setState(() {
        _status   = results[0] as MediaStatus;
        _playlist = results[1] as List<Track>;
        _loading  = false;
      });
    } catch (_) { setState(() => _loading = false); }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('MEDIA PLAYER')),
      body: _loading
        ? const Center(child: CircularProgressIndicator(color: JarvisColors.cyan, strokeWidth: 1.5))
        : SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(children: [
              // Now playing
              JPanel(label: 'NOW PLAYING', child: Column(children: [
                const SizedBox(height: 8),
                HudRing(size: 120, child: Center(child: Icon(
                  Icons.music_note,
                  color: JarvisColors.cyan.withOpacity(0.6), size: 28,
                ))),
                const SizedBox(height: 16),
                Text(
                  _status?.track?.title ?? 'NO TRACK',
                  style: GoogleFonts.orbitron(fontSize: 14, color: JarvisColors.textPrimary, letterSpacing: 1),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 4),
                Text(
                  _status?.track?.artist ?? '—',
                  style: GoogleFonts.shareTech(fontSize: 13, color: JarvisColors.textSecondary),
                ),
                const SizedBox(height: 20),
                // Controls
                Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                  _CtrlBtn(icon: Icons.skip_previous, onTap: () {}),
                  const SizedBox(width: 16),
                  _CtrlBtn(
                    icon: _status?.state == 'playing' ? Icons.pause : Icons.play_arrow,
                    size: 52,
                    onTap: () async {
                      if (_status?.state == 'playing') await _api.mediaPause();
                      else await _api.mediaPlay();
                      _load();
                    },
                  ),
                  const SizedBox(width: 16),
                  _CtrlBtn(icon: Icons.skip_next, onTap: () async { await _api.mediaNext(); _load(); }),
                ]),
                const SizedBox(height: 16),
                // Volume
                Row(children: [
                  const Icon(Icons.volume_down_outlined, color: JarvisColors.textSecondary, size: 16),
                  Expanded(child: SliderTheme(
                    data: SliderTheme.of(context).copyWith(
                      activeTrackColor: JarvisColors.cyan,
                      inactiveTrackColor: JarvisColors.border,
                      thumbColor: JarvisColors.cyan,
                      thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 6),
                      overlayShape: SliderComponentShape.noOverlay,
                    ),
                    child: Slider(
                      value: (_status?.volume ?? 80).toDouble(),
                      min: 0, max: 100,
                      onChanged: (v) async {
                        await _api.setVolume(v.toInt());
                        setState(() => _status = MediaStatus(
                          state: _status?.state ?? 'stopped',
                          track: _status?.track,
                          position: _status?.position ?? 0,
                          volume: v.toInt(),
                          shuffle: _status?.shuffle ?? false,
                          repeat: _status?.repeat ?? false,
                        ));
                      },
                    ),
                  )),
                  const Icon(Icons.volume_up_outlined, color: JarvisColors.textSecondary, size: 16),
                ]),
              ])),

              const SizedBox(height: 16),

              // Playlist
              JPanel(label: 'PLAYLIST (${_playlist.length})', child: _playlist.isEmpty
                ? Text('No tracks found in music directory', style: GoogleFonts.shareTech(fontSize: 13, color: JarvisColors.textSecondary))
                : Column(children: _playlist.take(20).toList().asMap().entries.map((e) {
                    final i = e.key; final t = e.value;
                    final isActive = _status?.track?.path == t.path;
                    return GestureDetector(
                      onTap: () async { await _api.mediaPlay(trackIndex: i); _load(); },
                      child: Container(
                        padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
                        decoration: BoxDecoration(
                          color: isActive ? JarvisColors.cyan.withOpacity(0.07) : Colors.transparent,
                          border: Border(bottom: BorderSide(color: JarvisColors.border.withOpacity(0.4))),
                        ),
                        child: Row(children: [
                          SizedBox(width: 28, child: isActive
                            ? const Icon(Icons.equalizer, color: JarvisColors.cyan, size: 14)
                            : Text('${i+1}', style: GoogleFonts.orbitron(fontSize: 10, color: JarvisColors.textSecondary))),
                          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(t.title, style: GoogleFonts.shareTech(fontSize: 13, color: isActive ? JarvisColors.cyan : JarvisColors.textPrimary), overflow: TextOverflow.ellipsis),
                            Text(t.artist, style: GoogleFonts.shareTech(fontSize: 11, color: JarvisColors.textSecondary), overflow: TextOverflow.ellipsis),
                          ])),
                          Text(t.durationFormatted, style: GoogleFonts.orbitron(fontSize: 10, color: JarvisColors.textSecondary)),
                        ]),
                      ),
                    );
                  }).toList()),
              ),
            ]),
          ),
    );
  }
}

class _CtrlBtn extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  final double size;
  const _CtrlBtn({required this.icon, required this.onTap, this.size = 36});

  @override
  Widget build(BuildContext context) => GestureDetector(
    onTap: onTap,
    child: Container(
      width: size, height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: JarvisColors.cyan.withOpacity(0.4)),
        color: JarvisColors.cyan.withOpacity(0.07),
      ),
      child: Icon(icon, color: JarvisColors.cyan, size: size * 0.46),
    ),
  );
}


// ════════════════════════════════════════
//  FILE MANAGER SCREEN
// ════════════════════════════════════════
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
      setState(() {
        _currentPath = data['path'];
        _entries = (data['entries'] as List).map((j) => FileEntry.fromJson(j)).toList();
      });
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Cannot open: $e'), backgroundColor: JarvisColors.bgCard),
      );
    }
    setState(() => _loading = false);
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
        title: const Text('FILE MANAGER'),
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
