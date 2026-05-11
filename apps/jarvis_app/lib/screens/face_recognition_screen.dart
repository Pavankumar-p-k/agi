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
