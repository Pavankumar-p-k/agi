// lib/screens/login_screen.dart
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import '../services/services.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> with TickerProviderStateMixin {
  final _emailCtrl    = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _nameCtrl     = TextEditingController();
  final _formKey      = GlobalKey<FormState>();

  bool _isLogin   = true;
  bool _loading   = false;
  bool _obscure   = true;
  String? _error;

  late AnimationController _fadeCtrl;
  late Animation<double>   _fadeAnim;
  late AnimationController _slideCtrl;
  late Animation<Offset>   _slideAnim;

  @override
  void initState() {
    super.initState();
    _fadeCtrl  = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200));
    _fadeAnim  = CurvedAnimation(parent: _fadeCtrl, curve: Curves.easeOut);
    _slideCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 900));
    _slideAnim = Tween<Offset>(begin: const Offset(0, 0.15), end: Offset.zero)
        .animate(CurvedAnimation(parent: _slideCtrl, curve: Curves.easeOut));
    _fadeCtrl.forward();
    _slideCtrl.forward();
  }

  @override
  void dispose() {
    _fadeCtrl.dispose(); _slideCtrl.dispose();
    _emailCtrl.dispose(); _passwordCtrl.dispose(); _nameCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() { _loading = true; _error = null; });

    final auth = context.read<AuthService>();
    try {
      if (_isLogin) {
        await auth.signInWithEmail(_emailCtrl.text.trim(), _passwordCtrl.text);
      } else {
        await auth.signUpWithEmail(
          _emailCtrl.text.trim(), _passwordCtrl.text, _nameCtrl.text.trim(),
        );
      }
    } catch (e) {
      setState(() { _error = e.toString(); });
    } finally {
      if (mounted) setState(() { _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return ScanlineOverlay(
      child: Scaffold(
        body: Stack(children: [
          // Background grid
          Positioned.fill(child: CustomPaint(painter: _GridPainter())),

          FadeTransition(
            opacity: _fadeAnim,
            child: SlideTransition(
              position: _slideAnim,
              child: SafeArea(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 40),
                  child: Column(
                    children: [
                      const SizedBox(height: 20),

                      // Logo
                      HudRing(
                        size: 130,
                        child: Center(
                          child: Text('J', style: GoogleFonts.orbitron(
                            fontSize: 32, fontWeight: FontWeight.w900,
                            color: JarvisColors.cyan,
                          )),
                        ),
                      ),

                      const SizedBox(height: 24),

                      Text('J.A.R.V.I.S', style: GoogleFonts.orbitron(
                        fontSize: 26, fontWeight: FontWeight.w900,
                        color: JarvisColors.cyan, letterSpacing: 6,
                      )),
                      const SizedBox(height: 6),
                      Text(
                        'JUST A RATHER VERY INTELLIGENT SYSTEM',
                        style: GoogleFonts.shareTech(
                          fontSize: 10, letterSpacing: 2,
                          color: JarvisColors.textSecondary,
                        ),
                        textAlign: TextAlign.center,
                      ),

                      const SizedBox(height: 48),

                      // Auth panel
                      JPanel(
                        label: _isLogin ? 'AUTHENTICATION' : 'CREATE ACCOUNT',
                        child: Form(
                          key: _formKey,
                          child: Column(children: [
                            if (!_isLogin) ...[
                              _JField(
                                controller: _nameCtrl,
                                hint: 'Display Name',
                                icon: Icons.person_outline,
                                validator: (v) => (v?.isEmpty ?? true) ? 'Enter your name' : null,
                              ),
                              const SizedBox(height: 14),
                            ],

                            _JField(
                              controller: _emailCtrl,
                              hint: 'Email Address',
                              icon: Icons.mail_outline,
                              keyboardType: TextInputType.emailAddress,
                              validator: (v) => (v?.contains('@') ?? false) ? null : 'Enter valid email',
                            ),
                            const SizedBox(height: 14),

                            _JField(
                              controller: _passwordCtrl,
                              hint: 'Password',
                              icon: Icons.lock_outline,
                              obscure: _obscure,
                              suffix: IconButton(
                                icon: Icon(
                                  _obscure ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                                  color: JarvisColors.textSecondary, size: 18,
                                ),
                                onPressed: () => setState(() => _obscure = !_obscure),
                              ),
                              validator: (v) => (v?.length ?? 0) >= 6 ? null : 'Min 6 characters',
                            ),

                            if (_error != null) ...[
                              const SizedBox(height: 12),
                              Container(
                                padding: const EdgeInsets.all(10),
                                decoration: BoxDecoration(
                                  border: Border.all(color: JarvisColors.red.withOpacity(0.5)),
                                  color: JarvisColors.red.withOpacity(0.08),
                                ),
                                child: Row(children: [
                                  const Icon(Icons.warning_outlined, color: JarvisColors.red, size: 14),
                                  const SizedBox(width: 8),
                                  Expanded(child: Text(_error!, style: GoogleFonts.shareTech(
                                    fontSize: 12, color: JarvisColors.red,
                                  ))),
                                ]),
                              ),
                            ],

                            const SizedBox(height: 20),

                            // Submit button
                            GestureDetector(
                              onTap: _loading ? null : _submit,
                              child: AnimatedContainer(
                                duration: const Duration(milliseconds: 200),
                                width: double.infinity,
                                padding: const EdgeInsets.symmetric(vertical: 14),
                                decoration: BoxDecoration(
                                  gradient: LinearGradient(colors: [
                                    JarvisColors.blue.withOpacity(_loading ? 0.3 : 0.5),
                                    JarvisColors.cyan.withOpacity(_loading ? 0.15 : 0.25),
                                  ]),
                                  border: Border.all(
                                    color: JarvisColors.cyan.withOpacity(_loading ? 0.3 : 0.6),
                                  ),
                                ),
                                child: Center(
                                  child: _loading
                                    ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(
                                        strokeWidth: 2, color: JarvisColors.cyan))
                                    : Text(
                                        _isLogin ? 'INITIALIZE SYSTEM' : 'CREATE PROFILE',
                                        style: GoogleFonts.orbitron(
                                          fontSize: 12, letterSpacing: 3,
                                          color: JarvisColors.cyan,
                                        ),
                                      ),
                                ),
                              ),
                            ),

                            const SizedBox(height: 16),

                            GestureDetector(
                              onTap: _loading
                                  ? null
                                  : () {
                                      final auth = context.read<AuthService>();
                                      auth.signInOffline(
                                        email: _emailCtrl.text.trim().isEmpty
                                            ? 'offline@local'
                                            : _emailCtrl.text.trim(),
                                        name: _nameCtrl.text.trim(),
                                      );
                                    },
                              child: Container(
                                width: double.infinity,
                                padding:
                                    const EdgeInsets.symmetric(vertical: 12),
                                decoration: BoxDecoration(
                                  border: Border.all(
                                    color: JarvisColors.orange.withOpacity(0.45),
                                  ),
                                  color: JarvisColors.orange.withOpacity(0.08),
                                ),
                                child: Center(
                                  child: Text(
                                    'CONTINUE OFFLINE',
                                    style: GoogleFonts.orbitron(
                                      fontSize: 11,
                                      letterSpacing: 2,
                                      color: JarvisColors.orange,
                                    ),
                                  ),
                                ),
                              ),
                            ),

                            const SizedBox(height: 14),

                            GestureDetector(
                              onTap: () => setState(() {
                                _isLogin = !_isLogin;
                                _error = null;
                              }),
                              child: RichText(
                                text: TextSpan(
                                  style: GoogleFonts.shareTech(
                                    fontSize: 12, color: JarvisColors.textSecondary,
                                  ),
                                  children: [
                                    TextSpan(text: _isLogin ? 'New user? ' : 'Have an account? '),
                                    TextSpan(
                                      text: _isLogin ? 'Create account' : 'Sign in',
                                      style: const TextStyle(color: JarvisColors.cyan),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ]),
                        ),
                      ),

                      const SizedBox(height: 24),
                      Text('v1.0.0 — STARK INDUSTRIES', style: GoogleFonts.orbitron(
                        fontSize: 9, letterSpacing: 2, color: JarvisColors.textDim,
                      )),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ]),
      ),
    );
  }
}

class _JField extends StatelessWidget {
  final TextEditingController controller;
  final String hint;
  final IconData icon;
  final bool obscure;
  final TextInputType? keyboardType;
  final String? Function(String?)? validator;
  final Widget? suffix;

  const _JField({
    required this.controller,
    required this.hint,
    required this.icon,
    this.obscure = false,
    this.keyboardType,
    this.validator,
    this.suffix,
  });

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      obscureText: obscure,
      keyboardType: keyboardType,
      validator: validator,
      style: GoogleFonts.shareTech(color: JarvisColors.textPrimary, fontSize: 14),
      decoration: InputDecoration(
        hintText: hint,
        prefixIcon: Icon(icon, size: 16, color: JarvisColors.textSecondary),
        suffixIcon: suffix,
      ),
    );
  }
}

class _GridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = JarvisColors.blue.withOpacity(0.04)
      ..strokeWidth = 0.5;

    for (double x = 0; x < size.width; x += 36) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
    for (double y = 0; y < size.height; y += 36) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
  }

  @override
  bool shouldRepaint(_) => false;
}
