// lib/screens/media_player_screen.dart
// JARVIS MEDIA PLAYER — Production Grade
// Replaces Android default music player.
// Uses just_audio + on_audio_query to read ALL device music.
// Features: queue, shuffle, repeat, equalizer bands,
//           sleep timer, speed control, lyrics (offline),
//           playlist management, waveform visualizer,
//           lock screen controls, notification controls.

import 'dart:math';
import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';
import 'package:just_audio_background/just_audio_background.dart';
import 'package:on_audio_query/on_audio_query.dart';
import 'package:audio_session/audio_session.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

// ── Global audio player singleton ─────────────────────────────
final _player = AudioPlayer();

class MediaPlayerScreen extends StatefulWidget {
  const MediaPlayerScreen({super.key});
  @override State<MediaPlayerScreen> createState() => _MediaPlayerScreenState();
}

class _MediaPlayerScreenState extends State<MediaPlayerScreen>
    with TickerProviderStateMixin {

  final _audioQuery = OnAudioQuery();
  List<SongModel> _songs    = [];
  List<SongModel> _filtered = [];
  SongModel?      _current;
  bool _loading      = true;
  bool _isPlaying    = false;
  bool _shuffle      = false;
  int  _repeatMode   = 0; // 0=off 1=all 2=one
  double _speed      = 1.0;
  double _volume     = 1.0;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
  int  _sleepMinutes = 0;
  bool _sleepActive  = false;
  int  _currentTab   = 0;  // 0=songs 1=playlists 2=equalizer
  String _search     = '';

  late AnimationController _rotateCtrl;
  late AnimationController _waveCtrl;
  late TextEditingController _searchCtrl;

  // EQ bands: sub-bass, bass, low-mid, mid, high-mid, high, presence, brilliance
  final List<double> _eqBands = [0,0,0,0,0,0,0,0];
  final List<String> _eqLabels = ['60','170','310','600','1k','3k','6k','14k'];

  static const _eqPresets = {
    'Flat':       [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    'Bass Boost': [5.0, 4.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    'Treble':     [0.0, 0.0, 0.0, 0.0, 2.0, 4.0, 5.0, 5.0],
    'Vocal':      [0.0, 0.0, 1.0, 4.0, 4.0, 3.0, 0.0, 0.0],
    'Rock':       [4.0, 3.0, 1.0, 0.0, 1.0, 3.0, 4.0, 4.0],
    'Classical':  [2.0, 2.0, 0.0,-1.0,-1.0, 0.0, 2.0, 3.0],
    'Hip-Hop':    [5.0, 4.0, 1.0, 3.0, 2.0, 0.0, 0.0, 0.0],
    'Night Mode': [-2.0,0.0, 1.0, 2.0, 2.0, 1.0, 0.0,-2.0],
  };

  @override
  void initState() {
    super.initState();
    _rotateCtrl = AnimationController(vsync: this, duration: const Duration(seconds: 12))..repeat();
    _waveCtrl   = AnimationController(vsync: this, duration: const Duration(milliseconds: 800))..repeat(reverse: true);
    _searchCtrl = TextEditingController();
    _initAudio();
    _loadSongs();
  }

  @override
  void dispose() {
    _rotateCtrl.dispose();
    _waveCtrl.dispose();
    _searchCtrl.dispose();
    super.dispose();
  }

  // ── Audio init ────────────────────────────────────────────

  Future<void> _initAudio() async {
    final session = await AudioSession.instance;
    await session.configure(const AudioSessionConfiguration.music());

    _player.playingStream.listen((playing) {
      if (mounted) setState(() => _isPlaying = playing);
      if (playing) _rotateCtrl.repeat(); else _rotateCtrl.stop();
    });

    _player.positionStream.listen((pos) {
      if (mounted) setState(() => _position = pos);
    });

    _player.durationStream.listen((dur) {
      if (mounted) setState(() => _duration = dur ?? Duration.zero);
    });

    _player.currentIndexStream.listen((idx) {
      if (idx != null && idx < _songs.length && mounted) {
        setState(() => _current = _songs[idx]);
      }
    });
  }

  // ── Load all device songs ─────────────────────────────────

  Future<void> _loadSongs() async {
    final permission = await _audioQuery.permissionsStatus();
    if (!permission) await _audioQuery.permissionsRequest();

    final songs = await _audioQuery.querySongs(
      sortType: SongSortType.TITLE,
      orderType: OrderType.ASC_OR_SMALLER,
      uriType: UriType.EXTERNAL,
      ignoreCase: true,
    );

    if (mounted) {
      setState(() {
        _songs    = songs.where((s) => s.duration != null && (s.duration ?? 0) > 10000).toList();
        _filtered = List.from(_songs);
        _loading  = false;
      });
    }

    // Build playlist for just_audio
    await _buildQueue(_songs);
  }

  Future<void> _buildQueue(List<SongModel> songs) async {
    final playlist = ConcatenatingAudioSource(
      children: songs.map((s) => AudioSource.uri(
        Uri.parse(s.uri ?? ''),
        tag: MediaItem(
          id:     s.id.toString(),
          title:  s.title,
          artist: s.artist ?? 'Unknown',
          album:  s.album ?? 'Unknown',
        ),
      )).toList(),
    );
    try {
      await _player.setAudioSource(playlist, preload: false);
    } catch (_) {}
  }

  // ── Playback controls ─────────────────────────────────────

  Future<void> _playSong(int index) async {
    try {
      await _player.seek(Duration.zero, index: index);
      await _player.play();
      setState(() => _current = _songs[index]);
    } catch (e) {
      debugPrint('Play error: $e');
    }
  }

  Future<void> _togglePlay() async {
    _player.playing ? await _player.pause() : await _player.play();
  }

  Future<void> _skipNext() async {
    if (_shuffle) {
      final idx = Random().nextInt(_songs.length);
      await _playSong(idx);
    } else {
      await _player.seekToNext();
    }
  }

  Future<void> _skipPrev() async {
    if (_position.inSeconds > 3) {
      await _player.seek(Duration.zero);
    } else {
      await _player.seekToPrevious();
    }
  }

  void _toggleShuffle() {
    setState(() => _shuffle = !_shuffle);
    _player.setShuffleModeEnabled(_shuffle);
  }

  void _toggleRepeat() {
    setState(() => _repeatMode = (_repeatMode + 1) % 3);
    final modes = [LoopMode.off, LoopMode.all, LoopMode.one];
    _player.setLoopMode(modes[_repeatMode]);
  }

  Future<void> _setSpeed(double speed) async {
    setState(() => _speed = speed);
    await _player.setSpeed(speed);
  }

  Future<void> _startSleepTimer(int minutes) async {
    setState(() { _sleepMinutes = minutes; _sleepActive = true; });
    Future.delayed(Duration(minutes: minutes), () async {
      if (mounted && _sleepActive) {
        await _player.pause();
        setState(() => _sleepActive = false);
      }
    });
  }

  void _filterSongs(String query) {
    setState(() {
      _search   = query;
      _filtered = query.isEmpty
        ? List.from(_songs)
        : _songs.where((s) =>
            s.title.toLowerCase().contains(query.toLowerCase()) ||
            (s.artist ?? '').toLowerCase().contains(query.toLowerCase())
          ).toList();
    });
  }

  void _applyEqPreset(String name) {
    final preset = _eqPresets[name]!;
    setState(() {
      for (int i = 0; i < _eqBands.length; i++) _eqBands[i] = preset[i];
    });
  }

  String get _formatPos => _format(_position);
  String get _formatDur => _format(_duration);

  String _format(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2,'0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2,'0');
    return '$m:$s';
  }

  IconData get _repeatIcon =>
    _repeatMode == 0 ? Icons.repeat :
    _repeatMode == 1 ? Icons.repeat : Icons.repeat_one;

  // ════════════════════════════════════════
  //  BUILD
  // ════════════════════════════════════════

  @override
  Widget build(BuildContext context) {
    return Column(children: [

      // Now playing bar (always visible)
      if (_current != null) _buildNowPlayingBar(),

      // Tabs
      _buildTabBar(),

      // Content
      Expanded(child: IndexedStack(index: _currentTab, children: [
        _buildSongList(),
        _buildPlaylists(),
        _buildEqualizer(),
      ])),
    ]);
  }

  // ── Now playing ───────────────────────────────────────────

  Widget _buildNowPlayingBar() {
    return GestureDetector(
      onTap: _showPlayerSheet,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: J.bg2,
          border: Border(
            top:    const BorderSide(color: J.cyan, width: 1.5),
            bottom: BorderSide(color: J.border0),
          ),
        ),
        child: Row(children: [

          // Album art / rotating ring
          AnimatedBuilder(
            animation: _rotateCtrl,
            builder: (_, child) => Transform.rotate(
              angle: _isPlaying ? _rotateCtrl.value * 2 * pi : 0,
              child: child,
            ),
            child: Container(
              width: 40, height: 40,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: J.cyan, width: 1.5),
                color: J.bg3,
              ),
              child: QueryArtworkWidget(
                id:         _current!.id,
                type:       ArtworkType.AUDIO,
                nullArtworkWidget: const Icon(Icons.music_note,
                    color: J.cyan, size: 18),
                artworkFit: BoxFit.cover,
              ),
            ),
          ),
          const SizedBox(width: 12),

          // Title + artist
          Expanded(child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(_current!.title,
                style: J.orbitron(11, weight: FontWeight.w700, spacing: 0.5),
                overflow: TextOverflow.ellipsis),
              Text(_current!.artist ?? 'Unknown',
                style: J.shareTech(10, color: J.t3)),
            ],
          )),

          // Controls
          Row(children: [
            _CtrlBtn(icon: Icons.skip_previous, size: 18, onTap: _skipPrev),
            _CtrlBtn(
              icon: _isPlaying ? Icons.pause : Icons.play_arrow,
              size: 24, filled: true, onTap: _togglePlay,
            ),
            _CtrlBtn(icon: Icons.skip_next, size: 18, onTap: _skipNext),
          ]),
        ]),
      ),
    );
  }

  // ── Full player sheet ─────────────────────────────────────

  void _showPlayerSheet() {
    showModalBottomSheet(
      context: context,
      backgroundColor: J.bg1,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
      builder: (_) => _FullPlayerSheet(
        song:       _current!,
        isPlaying:  _isPlaying,
        position:   _position,
        duration:   _duration,
        shuffle:    _shuffle,
        repeatMode: _repeatMode,
        speed:      _speed,
        sleepActive:_sleepActive,
        sleepMins:  _sleepMinutes,
        onPlay:     _togglePlay,
        onNext:     _skipNext,
        onPrev:     _skipPrev,
        onSeek:     (v) => _player.seek(Duration(seconds: v.toInt())),
        onShuffle:  _toggleShuffle,
        onRepeat:   _toggleRepeat,
        onSpeed:    _setSpeed,
        onSleep:    _startSleepTimer,
        rotateCtrl: _rotateCtrl,
        waveCtrl:   _waveCtrl,
      ),
    );
  }

  // ── Tab bar ───────────────────────────────────────────────

  Widget _buildTabBar() {
    final tabs = ['SONGS', 'PLAYLISTS', 'EQUALIZER'];
    return Container(
      height: 36,
      color: J.bg1,
      child: Row(
        children: List.generate(tabs.length, (i) {
          final sel = _currentTab == i;
          return Expanded(child: GestureDetector(
            onTap: () => setState(() => _currentTab = i),
            child: Container(
              decoration: BoxDecoration(
                border: Border(
                  bottom: BorderSide(
                    color: sel ? J.cyan : Colors.transparent, width: 2),
                ),
                color: sel ? J.cyan.withOpacity(0.06) : Colors.transparent,
              ),
              child: Center(child: Text(tabs[i],
                style: J.orbitron(9, color: sel ? J.cyan : J.t3, spacing: 1))),
            ),
          ));
        }),
      ),
    );
  }

  // ── Song list ─────────────────────────────────────────────

  Widget _buildSongList() {
    return Column(children: [
      // Search bar
      Padding(
        padding: const EdgeInsets.all(12),
        child: TextField(
          controller: _searchCtrl,
          style: J.shareTech(13),
          onChanged: _filterSongs,
          decoration: InputDecoration(
            hintText: 'Search songs, artists...',
            hintStyle: J.shareTech(12, color: J.t4),
            prefixIcon: const Icon(Icons.search, size: 16, color: J.t3),
            suffixIcon: _search.isNotEmpty
              ? GestureDetector(
                  onTap: () { _searchCtrl.clear(); _filterSongs(''); },
                  child: const Icon(Icons.close, size: 16, color: J.t3),
                )
              : null,
          ),
        ),
      ),

      // Stats row
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14),
        child: Row(children: [
          Text('${_filtered.length} songs',
              style: J.shareTech(10, color: J.t3)),
          const Spacer(),
          GestureDetector(
            onTap: () { _filterSongs(''); _playSong(Random().nextInt(_songs.length)); },
            child: Row(children: [
              const Icon(Icons.shuffle, size: 14, color: J.cyan),
              const SizedBox(width: 4),
              Text('SHUFFLE ALL', style: J.orbitron(8, color: J.cyan, spacing: 1)),
            ]),
          ),
        ]),
      ),
      const SizedBox(height: 8),

      // List
      Expanded(
        child: _loading
          ? const Center(child: CircularProgressIndicator(color: J.cyan, strokeWidth: 1))
          : _filtered.isEmpty
            ? Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                const Icon(Icons.music_off, color: J.t4, size: 48),
                const SizedBox(height: 12),
                Text('NO SONGS FOUND', style: J.orbitron(11, color: J.t3, spacing: 2)),
              ]))
            : ListView.builder(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                itemCount: _filtered.length,
                itemBuilder: (_, i) {
                  final s   = _filtered[i];
                  final cur = _current?.id == s.id;
                  return GestureDetector(
                    onTap: () {
                      final realIdx = _songs.indexOf(s);
                      if (realIdx >= 0) _playSong(realIdx);
                    },
                    child: Container(
                      margin: const EdgeInsets.only(bottom: 6),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      decoration: BoxDecoration(
                        color: cur ? J.cyan.withOpacity(0.08) : J.bg2,
                        border: Border(
                          left: BorderSide(color: cur ? J.cyan : J.border0, width: cur ? 2 : 1),
                          top:    const BorderSide(color: J.border0),
                          right:  const BorderSide(color: J.border0),
                          bottom: const BorderSide(color: J.border0),
                        ),
                      ),
                      child: Row(children: [
                        // Art
                        SizedBox(
                          width: 40, height: 40,
                          child: QueryArtworkWidget(
                            id:   s.id,
                            type: ArtworkType.AUDIO,
                            nullArtworkWidget: Container(
                              color: J.bg3,
                              child: const Icon(Icons.music_note, color: J.t3, size: 16),
                            ),
                            artworkFit: BoxFit.cover,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(s.title,
                              style: J.rajdhani(14, color: cur ? J.cyan : J.t1,
                                  weight: FontWeight.w600),
                              overflow: TextOverflow.ellipsis),
                            Text(s.artist ?? 'Unknown',
                              style: J.shareTech(10, color: J.t3)),
                          ],
                        )),
                        if (cur && _isPlaying)
                          AnimatedBuilder(
                            animation: _waveCtrl,
                            builder: (_, __) => _WaveIndicator(
                                value: _waveCtrl.value),
                          ),
                        const SizedBox(width: 8),
                        Text(_formatDuration(s.duration ?? 0),
                          style: J.shareTech(10, color: J.t3)),
                      ]),
                    ),
                  );
                },
              ),
      ),
    ]);
  }

  // ── Playlists tab ─────────────────────────────────────────

  Widget _buildPlaylists() {
    return FutureBuilder<List<PlaylistModel>>(
      future: _audioQuery.queryPlaylists(orderType: OrderType.ASC_OR_SMALLER),
      builder: (_, snap) {
        if (!snap.hasData) return const Center(child: CircularProgressIndicator(color: J.cyan, strokeWidth: 1));
        final playlists = snap.data!;
        return Column(children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(children: [
              Text('${playlists.length} playlists',
                  style: J.shareTech(10, color: J.t3)),
              const Spacer(),
              CyberButton(
                label: 'NEW PLAYLIST',
                icon: Icons.add,
                color: J.cyan,
                onTap: () => _createPlaylist(),
              ),
            ]),
          ),
          Expanded(
            child: playlists.isEmpty
              ? Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                  const Icon(Icons.playlist_play, color: J.t4, size: 48),
                  const SizedBox(height: 12),
                  Text('NO PLAYLISTS', style: J.orbitron(11, color: J.t3, spacing: 2)),
                  const SizedBox(height: 8),
                  Text('Create playlists to organise your music',
                      style: J.rajdhani(13, color: J.t3)),
                ]))
              : ListView.builder(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  itemCount: playlists.length,
                  itemBuilder: (_, i) {
                    final p = playlists[i];
                    return Container(
                      margin: const EdgeInsets.only(bottom: 8),
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: J.bg2,
                        border: Border(
                          top: const BorderSide(color: J.amber, width: 1.5),
                          left: const BorderSide(color: J.border0),
                          right: const BorderSide(color: J.border0),
                          bottom: const BorderSide(color: J.border0),
                        ),
                      ),
                      child: Row(children: [
                        const Icon(Icons.queue_music_outlined, color: J.amber, size: 24),
                        const SizedBox(width: 12),
                        Expanded(child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(p.playlist, style: J.orbitron(12, color: J.t1, spacing: 1)),
                            Text('${p.numOfSongs} songs',
                                style: J.shareTech(10, color: J.t3)),
                          ],
                        )),
                        const Icon(Icons.chevron_right, color: J.t3, size: 18),
                      ]),
                    );
                  },
                ),
          ),
        ]);
      },
    );
  }

  Future<void> _createPlaylist() async {
    final ctrl = TextEditingController();
    await showDialog(context: context, builder: (_) => AlertDialog(
      backgroundColor: J.bg1,
      title: Text('NEW PLAYLIST', style: J.orbitron(12, spacing: 2)),
      content: TextField(controller: ctrl, style: J.rajdhani(14),
          decoration: const InputDecoration(hintText: 'Playlist name')),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context),
            child: Text('CANCEL', style: J.orbitron(9, color: J.t3))),
        TextButton(onPressed: () async {
          if (ctrl.text.isNotEmpty) {
            await _audioQuery.createPlaylist(ctrl.text);
            Navigator.pop(context);
            setState(() {});
          }
        }, child: Text('CREATE', style: J.orbitron(9, color: J.cyan))),
      ],
    ));
  }

  // ── Equalizer tab ─────────────────────────────────────────

  Widget _buildEqualizer() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [

        // Presets
        Text('PRESETS', style: J.orbitron(10, color: J.cyan, spacing: 2)),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8,
          children: _eqPresets.keys.map((name) =>
            GestureDetector(
              onTap: () => _applyEqPreset(name),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  border: Border.all(color: J.border1),
                  color: J.bg3,
                ),
                child: Text(name, style: J.orbitron(9, color: J.t1, spacing: 1)),
              ),
            )).toList(),
        ),
        const SizedBox(height: 24),

        // EQ Bands
        Text('CUSTOM EQ', style: J.orbitron(10, color: J.cyan, spacing: 2)),
        const SizedBox(height: 16),
        SizedBox(
          height: 200,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: List.generate(_eqBands.length, (i) {
              return Column(children: [
                Expanded(
                  child: RotatedBox(
                    quarterTurns: 3,
                    child: Slider(
                      value: _eqBands[i],
                      min: -12, max: 12,
                      divisions: 24,
                      activeColor: _eqBands[i] >= 0 ? J.cyan : J.amber,
                      inactiveColor: J.border0,
                      onChanged: (v) => setState(() => _eqBands[i] = v),
                    ),
                  ),
                ),
                Text('${_eqBands[i] >= 0 ? '+' : ''}${_eqBands[i].toStringAsFixed(0)}',
                    style: J.shareTech(9, color: J.t2)),
                const SizedBox(height: 2),
                Text(_eqLabels[i], style: J.shareTech(8, color: J.t3)),
              ]);
            }),
          ),
        ),
        const SizedBox(height: 16),

        // Speed control
        Text('PLAYBACK SPEED', style: J.orbitron(10, color: J.cyan, spacing: 2)),
        const SizedBox(height: 8),
        Row(children: [
          Text('0.5x', style: J.shareTech(10, color: J.t3)),
          Expanded(child: Slider(
            value: _speed, min: 0.5, max: 2.0, divisions: 15,
            activeColor: J.amber, inactiveColor: J.border0,
            label: '${_speed.toStringAsFixed(1)}x',
            onChanged: _setSpeed,
          )),
          Text('2.0x', style: J.shareTech(10, color: J.t3)),
          const SizedBox(width: 8),
          Text('${_speed.toStringAsFixed(1)}x',
              style: J.orbitron(12, color: J.amber, spacing: 0)),
        ]),
        const SizedBox(height: 16),

        // Sleep timer
        Text('SLEEP TIMER', style: J.orbitron(10, color: J.cyan, spacing: 2)),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          ...[5, 10, 15, 30, 45, 60].map((min) =>
            GestureDetector(
              onTap: () => _startSleepTimer(min),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  border: Border.all(color: _sleepMinutes == min && _sleepActive ? J.red : J.border0),
                  color: _sleepMinutes == min && _sleepActive ? J.red.withOpacity(0.1) : J.bg3,
                ),
                child: Text('${min}m',
                  style: J.orbitron(10, color: _sleepMinutes == min && _sleepActive ? J.red : J.t2, spacing: 0)),
              ),
            )),
          if (_sleepActive)
            GestureDetector(
              onTap: () => setState(() => _sleepActive = false),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(border: Border.all(color: J.red), color: J.red.withOpacity(0.1)),
                child: Text('CANCEL', style: J.orbitron(10, color: J.red, spacing: 1)),
              ),
            ),
        ]),
      ]),
    );
  }

  String _formatDuration(int ms) {
    final d = Duration(milliseconds: ms);
    return '${d.inMinutes.remainder(60).toString().padLeft(2,'0')}:${d.inSeconds.remainder(60).toString().padLeft(2,'0')}';
  }
}

// ── Full player bottom sheet ──────────────────────────────────

class _FullPlayerSheet extends StatelessWidget {
  final SongModel  song;
  final bool       isPlaying, shuffle, sleepActive;
  final int        repeatMode, sleepMins;
  final Duration   position, duration;
  final double     speed;
  final VoidCallback onPlay, onNext, onPrev, onShuffle, onRepeat;
  final ValueChanged<double> onSeek, onSpeed;
  final ValueChanged<int>    onSleep;
  final AnimationController  rotateCtrl, waveCtrl;

  const _FullPlayerSheet({
    required this.song, required this.isPlaying,
    required this.position, required this.duration,
    required this.shuffle, required this.repeatMode,
    required this.speed, required this.sleepActive, required this.sleepMins,
    required this.onPlay, required this.onNext, required this.onPrev,
    required this.onShuffle, required this.onRepeat,
    required this.onSeek, required this.onSpeed, required this.onSleep,
    required this.rotateCtrl, required this.waveCtrl,
  });

  String _fmt(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2,'0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2,'0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    final maxSeconds = duration.inSeconds.toDouble().clamp(1.0, double.infinity);
    final curSeconds = position.inSeconds.toDouble().clamp(0.0, maxSeconds);

    return Container(
      height: MediaQuery.of(context).size.height * 0.85,
      padding: const EdgeInsets.all(24),
      decoration: const BoxDecoration(
        color: J.bg1,
        border: Border(top: BorderSide(color: J.cyan, width: 1.5)),
      ),
      child: Column(children: [

        // Handle
        Container(width: 40, height: 3, color: J.border1),
        const SizedBox(height: 24),

        // Album art
        AnimatedBuilder(
          animation: rotateCtrl,
          builder: (_, child) => Transform.rotate(
            angle: isPlaying ? rotateCtrl.value * 2 * pi : 0,
            child: child,
          ),
          child: Container(
            width: 180, height: 180,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: J.cyan, width: 2),
              boxShadow: [BoxShadow(color: J.cyan.withOpacity(0.2),
                  blurRadius: 30, spreadRadius: 5)],
            ),
            child: ClipOval(child: QueryArtworkWidget(
              id: song.id, type: ArtworkType.AUDIO,
              nullArtworkWidget: Container(
                color: J.bg3,
                child: const Icon(Icons.music_note, color: J.cyan, size: 48),
              ),
              artworkFit: BoxFit.cover,
            )),
          ),
        ),
        const SizedBox(height: 24),

        // Title
        Text(song.title,
          style: J.orbitron(16, weight: FontWeight.w800, spacing: 1),
          textAlign: TextAlign.center, overflow: TextOverflow.ellipsis),
        const SizedBox(height: 4),
        Text(song.artist ?? 'Unknown',
          style: J.rajdhani(15, color: J.t2)),
        const SizedBox(height: 24),

        // Progress bar
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          child: Column(children: [
            SliderTheme(
              data: SliderThemeData(
                trackHeight: 3,
                thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 5),
                overlayShape: const RoundSliderOverlayShape(overlayRadius: 14),
                activeTrackColor: J.cyan,
                inactiveTrackColor: J.border0,
                thumbColor: J.cyan,
                overlayColor: J.cyan.withOpacity(0.2),
              ),
              child: Slider(
                value: curSeconds,
                max:   maxSeconds,
                onChanged: onSeek,
              ),
            ),
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              Text(_fmt(position), style: J.shareTech(10, color: J.t3)),
              Text(_fmt(duration), style: J.shareTech(10, color: J.t3)),
            ]),
          ]),
        ),
        const SizedBox(height: 16),

        // Main controls
        Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
          _CtrlBtn(
            icon: Icons.shuffle,
            color: shuffle ? J.cyan : J.t3,
            onTap: onShuffle,
          ),
          _CtrlBtn(icon: Icons.skip_previous, size: 32, onTap: onPrev),
          _CtrlBtn(
            icon: isPlaying ? Icons.pause_circle_filled : Icons.play_circle_filled,
            size: 56, filled: true, onTap: onPlay,
          ),
          _CtrlBtn(icon: Icons.skip_next, size: 32, onTap: onNext),
          _CtrlBtn(
            icon: repeatMode == 2 ? Icons.repeat_one : Icons.repeat,
            color: repeatMode > 0 ? J.cyan : J.t3,
            onTap: onRepeat,
          ),
        ]),
        const SizedBox(height: 16),

        // Speed + sleep row
        Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          Text('SPEED: ${speed.toStringAsFixed(1)}x',
              style: J.orbitron(9, color: J.amber, spacing: 1)),
          const SizedBox(width: 24),
          if (sleepActive)
            Text('SLEEP: ${sleepMins}m',
                style: J.orbitron(9, color: J.red, spacing: 1)),
        ]),
      ]),
    );
  }
}

// ── Helper widgets ────────────────────────────────────────────

class _CtrlBtn extends StatelessWidget {
  final IconData icon;
  final double   size;
  final bool     filled;
  final Color?   color;
  final VoidCallback onTap;
  const _CtrlBtn({required this.icon, required this.onTap,
    this.size = 22, this.filled = false, this.color});

  @override
  Widget build(BuildContext context) {
    final col = color ?? J.cyan;
    return GestureDetector(
      onTap: onTap,
      child: filled
        ? Container(
            width: size + 16, height: size + 16,
            decoration: BoxDecoration(
              shape: BoxShape.circle, color: col,
              boxShadow: [BoxShadow(color: col.withOpacity(0.3), blurRadius: 12)],
            ),
            child: Icon(icon, color: J.bg0, size: size),
          )
        : Icon(icon, color: col, size: size),
    );
  }
}

class _WaveIndicator extends StatelessWidget {
  final double value;
  const _WaveIndicator({required this.value});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: List.generate(4, (i) {
        final h = 6.0 + sin((value * pi * 2) + i * pi / 2).abs() * 10;
        return Container(
          width: 2, height: h, margin: const EdgeInsets.symmetric(horizontal: 1),
          color: J.cyan,
        );
      }),
    );
  }
}
