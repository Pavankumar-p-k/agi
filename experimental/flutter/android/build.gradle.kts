allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
subprojects {
    project.evaluationDependsOn(":app")
}

// Force consistent Java/Kotlin targets across all subprojects.
subprojects {
    plugins.withId("com.android.library") {
        tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile>().configureEach {
            compilerOptions {
                jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_1_8)
            }
        }
    }
    plugins.withId("com.android.application") {
        tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile>().configureEach {
            compilerOptions {
                jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
            }
        }
    }
}

// Workaround for plugins missing `namespace` on AGP 8+.
// If a library module doesn't define namespace, infer it from its AndroidManifest.xml.
subprojects {
    plugins.withId("com.android.library") {
        extensions.configure<com.android.build.gradle.LibraryExtension> {
            if (namespace == null && project.name == "on_audio_query_android") {
                namespace = "com.lucasjosino.on_audio_query"
            }
            if (namespace == null) {
                val manifestFile = sourceSets.getByName("main").manifest.srcFile
                if (manifestFile.exists()) {
                    val text = manifestFile.readText()
                    val match = Regex("package\\s*=\\s*\"([^\"]+)\"").find(text)
                    if (match != null) {
                        namespace = match.groupValues[1]
                    }
                }
            }
        }
    }
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
