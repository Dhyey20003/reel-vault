// ReelVault Android project.
// Pass -Preelvault.coreOnly=true to build/test only the pure-Kotlin :core module without the Android SDK
// or Google's Maven repository (the APK itself needs both).
val coreOnly = gradle.startParameter.projectProperties["reelvault.coreOnly"] == "true"

pluginManagement {
    repositories {
        if (gradle.startParameter.projectProperties["reelvault.coreOnly"] != "true") {
            google {
                content {
                    includeGroupByRegex("com\\.android.*")
                    includeGroupByRegex("com\\.google.*")
                    includeGroupByRegex("androidx.*")
                }
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
    // Versions live here so that a core-only build never has to resolve the Android plugin.
    plugins {
        id("com.android.application") version "8.9.1"
        id("org.jetbrains.kotlin.android") version "2.1.20"
        id("org.jetbrains.kotlin.jvm") version "2.1.20"
        id("org.jetbrains.kotlin.plugin.compose") version "2.1.20"
        id("com.google.devtools.ksp") version "2.1.20-1.0.32"
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        if (gradle.startParameter.projectProperties["reelvault.coreOnly"] != "true") {
            google()
        }
        mavenCentral()
    }
}

rootProject.name = "ReelVault"
include(":core")
if (!coreOnly) {
    include(":app")
}
