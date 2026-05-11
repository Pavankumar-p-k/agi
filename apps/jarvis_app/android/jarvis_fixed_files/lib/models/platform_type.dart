// lib/models/platform_type.dart

enum PlatformType {
  whatsapp,
  instagram,
  telegram,
  discord,
  linkedin,
  snapchat,
  sms,
  unknown;

  /// Android package name used to match incoming notifications
  String get packageName {
    switch (this) {
      case PlatformType.whatsapp:   return 'com.whatsapp';
      case PlatformType.instagram:  return 'com.instagram.android';
      case PlatformType.telegram:   return 'org.telegram.messenger';
      case PlatformType.discord:    return 'com.discord';
      case PlatformType.linkedin:   return 'com.linkedin.android';
      case PlatformType.snapchat:   return 'com.snapchat.android';
      case PlatformType.sms:        return 'com.google.android.apps.messaging';
      case PlatformType.unknown:    return '';
    }
  }

  /// Human-readable label shown in UI
  String get label {
    switch (this) {
      case PlatformType.whatsapp:   return 'WhatsApp';
      case PlatformType.instagram:  return 'Instagram';
      case PlatformType.telegram:   return 'Telegram';
      case PlatformType.discord:    return 'Discord';
      case PlatformType.linkedin:   return 'LinkedIn';
      case PlatformType.snapchat:   return 'Snapchat';
      case PlatformType.sms:        return 'SMS';
      case PlatformType.unknown:    return 'Unknown';
    }
  }

  /// Match a package name string to a PlatformType
  static PlatformType fromPackage(String packageName) {
    for (final p in PlatformType.values) {
      if (p.packageName.isNotEmpty && packageName.contains(p.packageName)) {
        return p;
      }
    }
    // Samsung SMS app
    if (packageName.contains('com.samsung.android.messaging')) {
      return PlatformType.sms;
    }
    return PlatformType.unknown;
  }

  /// Match a plain string name (stored in DB / settings)
  static PlatformType fromString(String value) {
    switch (value.toLowerCase().trim()) {
      case 'whatsapp':   return PlatformType.whatsapp;
      case 'instagram':  return PlatformType.instagram;
      case 'telegram':   return PlatformType.telegram;
      case 'discord':    return PlatformType.discord;
      case 'linkedin':   return PlatformType.linkedin;
      case 'snapchat':   return PlatformType.snapchat;
      case 'sms':        return PlatformType.sms;
      default:           return PlatformType.unknown;
    }
  }
}
