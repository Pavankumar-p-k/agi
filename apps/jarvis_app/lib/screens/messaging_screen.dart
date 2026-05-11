import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../services/device_automation_service.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class MessagingScreen extends StatefulWidget {
  const MessagingScreen({super.key});

  @override
  State<MessagingScreen> createState() => _MessagingScreenState();
}

class _MessagingScreenState extends State<MessagingScreen> {
  final _automation = DeviceAutomationService();
  final _recipientCtrl = TextEditingController();
  final _messageCtrl = TextEditingController();

  String _platform = 'sms';
  bool _loading = false;
  String? _result;

  @override
  void dispose() {
    _recipientCtrl.dispose();
    _messageCtrl.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final recipient = _recipientCtrl.text.trim();
    final message = _messageCtrl.text.trim();
    if (recipient.isEmpty) return;

    setState(() {
      _loading = true;
      _result = null;
    });

    try {
      switch (_platform) {
        case 'whatsapp':
          await _automation.composeWhatsApp(number: recipient, text: message);
          break;
        case 'email':
          await _automation.composeEmail(email: recipient, body: message);
          break;
        case 'sms':
        default:
          await _automation.composeSms(recipient, message);
          break;
      }

      if (!mounted) return;
      setState(() {
        _result = 'Draft opened in the target app.';
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _result = 'Failed to open draft: $e';
      });
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('MESSAGE COMPOSER')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            JPanel(
              label: 'PLATFORM',
              child: Row(
                children: [
                  _PlatformChip(
                    label: 'SMS',
                    icon: Icons.sms_outlined,
                    selected: _platform == 'sms',
                    onTap: () => setState(() => _platform = 'sms'),
                    color: JarvisColors.green,
                  ),
                  const SizedBox(width: 10),
                  _PlatformChip(
                    label: 'WHATSAPP',
                    icon: Icons.chat_bubble_outline,
                    selected: _platform == 'whatsapp',
                    onTap: () => setState(() => _platform = 'whatsapp'),
                    color: JarvisColors.orange,
                  ),
                  const SizedBox(width: 10),
                  _PlatformChip(
                    label: 'EMAIL',
                    icon: Icons.mail_outline,
                    selected: _platform == 'email',
                    onTap: () => setState(() => _platform = 'email'),
                    color: JarvisColors.cyan,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            JPanel(
              label: 'COMPOSE',
              child: Column(
                children: [
                  TextField(
                    controller: _recipientCtrl,
                    style: GoogleFonts.shareTech(color: JarvisColors.textPrimary),
                    decoration: InputDecoration(
                      hintText: _platform == 'email'
                          ? 'Email address'
                          : 'Phone number or WhatsApp number',
                      prefixIcon: const Icon(
                        Icons.person_outline,
                        color: JarvisColors.textSecondary,
                        size: 16,
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _messageCtrl,
                    style: GoogleFonts.shareTech(
                      color: JarvisColors.textPrimary,
                      fontSize: 13,
                    ),
                    maxLines: 4,
                    decoration: const InputDecoration(
                      hintText: 'Message content...',
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (_result != null)
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(10),
                      margin: const EdgeInsets.only(bottom: 12),
                      decoration: BoxDecoration(
                        border: Border.all(
                          color: _result!.startsWith('Draft')
                              ? JarvisColors.green
                              : JarvisColors.red,
                          width: 0.8,
                        ),
                        color: (_result!.startsWith('Draft')
                                ? JarvisColors.green
                                : JarvisColors.red)
                            .withOpacity(0.07),
                      ),
                      child: Text(
                        _result!,
                        style: GoogleFonts.shareTech(
                          fontSize: 13,
                          color: _result!.startsWith('Draft')
                              ? JarvisColors.green
                              : JarvisColors.red,
                        ),
                      ),
                    ),
                  SizedBox(
                    width: double.infinity,
                    child: JButton(
                      label: _loading ? 'OPENING...' : 'OPEN DRAFT',
                      icon: Icons.send,
                      onTap: _loading ? null : _send,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            JPanel(
              label: 'NOTE',
              child: Text(
                'Android opens the target app with a prefilled draft. The app does not send messages silently in the background.',
                style: GoogleFonts.shareTech(
                  fontSize: 11,
                  color: JarvisColors.textSecondary,
                  height: 1.5,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PlatformChip extends StatelessWidget {
  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;
  final Color color;

  const _PlatformChip({
    required this.label,
    required this.icon,
    required this.selected,
    required this.onTap,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: selected ? color.withOpacity(0.12) : Colors.transparent,
            border: Border.all(color: selected ? color : JarvisColors.border),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                icon,
                size: 14,
                color: selected ? color : JarvisColors.textSecondary,
              ),
              const SizedBox(width: 6),
              Text(
                label,
                style: GoogleFonts.orbitron(
                  fontSize: 10,
                  letterSpacing: 1.5,
                  color: selected ? color : JarvisColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
