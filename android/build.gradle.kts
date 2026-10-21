// Root project. Plugin versions are declared in settings.gradle.kts (pluginManagement.plugins).
tasks.register("clean", Delete::class) {
    delete(rootProject.layout.buildDirectory)
}
