"""brain/repair_modules/fix_gradle.py
Deterministic Gradle build file repair.
Writes proper build.gradle, settings.gradle, gradle.properties.
"""
from pathlib import Path


APP_BUILD_GRADLE = """plugins {
    id 'com.android.application'
    id 'org.jetbrains.kotlin.android' version '1.9.22' apply false
}

android {
    namespace 'com.example.app'
    compileSdk 34

    defaultConfig {
        applicationId 'com.example.app'
        minSdk 26
        targetSdk 34
        versionCode 1
        versionName '1.0'
        testInstrumentationRunner 'androidx.test.runner.AndroidJUnitRunner'
    }

    buildTypes {
        release {
            minifyEnabled false
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
    }

    compileOptions {
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }
}

dependencies {
    implementation 'androidx.core:core-ktx:1.12.0'
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.11.0'
    implementation 'androidx.constraintlayout:constraintlayout:2.1.4'
    implementation 'androidx.recyclerview:recyclerview:1.3.2'
    implementation 'androidx.cardview:cardview:1.0.0'
    implementation 'androidx.lifecycle:lifecycle-viewmodel-ktx:2.7.0'
    implementation 'androidx.lifecycle:lifecycle-livedata-ktx:2.7.0'
    implementation 'androidx.room:room-runtime:2.6.1'
    implementation 'androidx.navigation:navigation-fragment-ktx:2.7.7'
    implementation 'androidx.navigation:navigation-ui-ktx:2.7.7'
    implementation 'com.google.code.gson:gson:2.10.1'
    testImplementation 'junit:junit:4.13.2'
    testImplementation 'org.mockito:mockito-core:5.7.0'
    androidTestImplementation 'androidx.test.ext:junit:1.1.5'
    androidTestImplementation 'androidx.test.espresso:espresso-core:3.5.1'
}
"""


def fix_gradle(project_dir: str, errors: list[dict]) -> list[str]:
    """Fix or create Gradle build files."""
    created = []
    proj = Path(project_dir)

    app_build = proj / "app" / "build.gradle"
    if not app_build.exists() or any("build.gradle" in e.get("message", "") for e in errors):
        app_build.parent.mkdir(parents=True, exist_ok=True)
        app_build.write_text(APP_BUILD_GRADLE, encoding="utf-8")
        created.append(str(app_build))

    settings = proj / "settings.gradle"
    if not settings.exists():
        settings.write_text("rootProject.name = 'MyApp'\ninclude ':app'\n", encoding="utf-8")
        created.append(str(settings))

    properties = proj / "gradle.properties"
    if not properties.exists():
        props = (
            "org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8\n"
            "android.useAndroidX=true\n"
            "android.nonTransitiveRClass=true\n"
        )
        properties.write_text(props, encoding="utf-8")
        created.append(str(properties))

    return created
