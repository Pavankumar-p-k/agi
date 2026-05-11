import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../services/device_automation_service.dart';
import '../services/device_data_service.dart';

const _bg = Color(0xFF010A12);
const _bgCard = Color(0xFF061420);
const _cyan = Color(0xFF00E5FF);
const _green = Color(0xFF00FFAA);
const _orange = Color(0xFFFF6A00);
const _border = Color(0xFF0D3348);
const _textPri = Color(0xFFB0EEFF);
const _textSec = Color(0xFF4A7A8A);

class ContactsScreen extends StatefulWidget {
  const ContactsScreen({super.key});

  @override
  State<ContactsScreen> createState() => _ContactsScreenState();
}

class _ContactsScreenState extends State<ContactsScreen> {
  final _deviceData = DeviceDataService();
  final _automation = DeviceAutomationService();
  final _searchCtrl = TextEditingController();

  List<Map<String, dynamic>> _contacts = <Map<String, dynamic>>[];
  List<Map<String, dynamic>> _filtered = <Map<String, dynamic>>[];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final contacts = await _deviceData.getContacts(limit: 1000);
      contacts.sort((a, b) {
        final left = (a['name'] ?? '').toString().toLowerCase();
        final right = (b['name'] ?? '').toString().toLowerCase();
        return left.compareTo(right);
      });
      if (!mounted) return;
      setState(() {
        _contacts = contacts;
        _filtered = List<Map<String, dynamic>>.from(contacts);
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  void _filter(String query) {
    final q = query.trim().toLowerCase();
    setState(() {
      _filtered = q.isEmpty
          ? List<Map<String, dynamic>>.from(_contacts)
          : _contacts.where((contact) {
              final name = (contact['name'] ?? '').toString().toLowerCase();
              final number = (contact['number'] ?? '').toString().toLowerCase();
              return name.contains(q) || number.contains(q);
            }).toList();
    });
  }

  Future<void> _composeSms(Map<String, dynamic> contact) async {
    final number = (contact['number'] ?? '').toString();
    if (number.isEmpty) return;
    await _automation.composeSms(number, '');
  }

  Future<void> _composeWhatsApp(Map<String, dynamic> contact) async {
    final number = (contact['number'] ?? '').toString();
    if (number.isEmpty) return;
    await _automation.composeWhatsApp(number: number, text: '');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: _bg,
        elevation: 0,
        title: Text(
          'DEVICE CONTACTS',
          style: GoogleFonts.orbitron(
            fontSize: 14,
            color: _cyan,
            letterSpacing: 3,
          ),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: _cyan),
            onPressed: _load,
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: TextField(
              controller: _searchCtrl,
              onChanged: _filter,
              style: GoogleFonts.shareTech(color: _textPri),
              decoration: InputDecoration(
                hintText: 'Search device contacts',
                prefixIcon: const Icon(Icons.search, color: _textSec, size: 18),
                suffixIcon: _searchCtrl.text.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.clear, color: _textSec, size: 16),
                        onPressed: () {
                          _searchCtrl.clear();
                          _filter('');
                        },
                      ),
                filled: true,
                fillColor: _bgCard,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(4),
                  borderSide: const BorderSide(color: _border),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(4),
                  borderSide: const BorderSide(color: _border),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(4),
                  borderSide: const BorderSide(color: _cyan),
                ),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 8),
            child: Row(
              children: [
                Text(
                  '${_filtered.length} contacts',
                  style: GoogleFonts.orbitron(
                    fontSize: 9,
                    letterSpacing: 2,
                    color: _textSec,
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: _loading
                ? const Center(
                    child: CircularProgressIndicator(color: _cyan, strokeWidth: 1.5),
                  )
                : _filtered.isEmpty
                    ? Center(
                        child: Text(
                          'No device contacts available',
                          style: GoogleFonts.shareTech(
                            fontSize: 13,
                            color: _textSec,
                          ),
                        ),
                      )
                    : ListView.builder(
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        itemCount: _filtered.length,
                        itemBuilder: (_, index) {
                          final contact = _filtered[index];
                          final name = (contact['name'] ?? 'Unknown').toString();
                          final number = (contact['number'] ?? '').toString();
                          final initials = name.isEmpty ? '?' : name[0].toUpperCase();
                          return Padding(
                            padding: const EdgeInsets.only(bottom: 10),
                            child: Container(
                              decoration: BoxDecoration(
                                color: _bgCard,
                                border: Border.all(color: _border),
                              ),
                              child: Padding(
                                padding: const EdgeInsets.all(14),
                                child: Column(
                                  children: [
                                    Row(
                                      children: [
                                        Container(
                                          width: 42,
                                          height: 42,
                                          decoration: BoxDecoration(
                                            shape: BoxShape.circle,
                                            border: Border.all(color: _cyan.withOpacity(0.35)),
                                            color: _cyan.withOpacity(0.08),
                                          ),
                                          child: Center(
                                            child: Text(
                                              initials,
                                              style: GoogleFonts.orbitron(
                                                fontSize: 15,
                                                color: _cyan,
                                                fontWeight: FontWeight.w700,
                                              ),
                                            ),
                                          ),
                                        ),
                                        const SizedBox(width: 12),
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                              Text(
                                                name,
                                                style: GoogleFonts.orbitron(
                                                  fontSize: 13,
                                                  color: _textPri,
                                                  letterSpacing: 1,
                                                ),
                                              ),
                                              const SizedBox(height: 4),
                                              Text(
                                                number.isEmpty ? 'No phone number' : number,
                                                style: GoogleFonts.shareTech(
                                                  fontSize: 12,
                                                  color: _textSec,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: 12),
                                    Row(
                                      children: [
                                        Expanded(
                                          child: _ActionButton(
                                            label: 'DIAL',
                                            icon: Icons.call_outlined,
                                            color: _cyan,
                                            onTap: number.isEmpty
                                                ? null
                                                : () => _deviceData.openDialer(number),
                                          ),
                                        ),
                                        const SizedBox(width: 8),
                                        Expanded(
                                          child: _ActionButton(
                                            label: 'SMS',
                                            icon: Icons.sms_outlined,
                                            color: _green,
                                            onTap: number.isEmpty
                                                ? null
                                                : () => _composeSms(contact),
                                          ),
                                        ),
                                        const SizedBox(width: 8),
                                        Expanded(
                                          child: _ActionButton(
                                            label: 'WHATSAPP',
                                            icon: Icons.chat_bubble_outline,
                                            color: _orange,
                                            onTap: number.isEmpty
                                                ? null
                                                : () => _composeWhatsApp(contact),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final VoidCallback? onTap;

  const _ActionButton({
    required this.label,
    required this.icon,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: enabled ? color.withOpacity(0.08) : Colors.transparent,
          border: Border.all(color: enabled ? color.withOpacity(0.35) : _border),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 14, color: enabled ? color : _textSec),
            const SizedBox(width: 6),
            Text(
              label,
              style: GoogleFonts.orbitron(
                fontSize: 9,
                letterSpacing: 1.2,
                color: enabled ? color : _textSec,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
