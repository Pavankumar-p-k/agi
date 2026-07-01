import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class PlaceholderScreen extends StatelessWidget {
  final String title;
  const PlaceholderScreen({super.key, required this.title});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: JarvisColors.bg,
      appBar: AppBar(
        title: Text(title.toUpperCase(), style: J.orbitron(14, spacing: 4)),
      ),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const HudRing(size: 80),
            const SizedBox(height: 20),
            Text(
              'MODULE UNDER CONSTRUCTION',
              style: J.orbitron(12, color: JarvisColors.orange, spacing: 2),
            ),
            const SizedBox(height: 8),
            Text(
              'This surface is being synchronized with the JARVIS core.',
              style: J.shareTech(12, color: JarvisColors.textDim),
            ),
          ],
        ),
      ),
    );
  }
}
