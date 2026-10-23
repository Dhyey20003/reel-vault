plugins {
    id("org.jetbrains.kotlin.jvm")
}

// Compile for Java 17 bytecode with whatever JDK (17 or newer) runs Gradle; no toolchain download needed.
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
kotlin {
    compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) }
}

dependencies {
    // Android ships org.json at runtime; on the JVM (unit tests) we use the Maven artifact.
    compileOnly("org.json:json:20250107")
    testImplementation("org.json:json:20250107")
    testImplementation("org.jetbrains.kotlin:kotlin-test")
    testImplementation("org.jetbrains.kotlin:kotlin-test-junit")
}

tasks.test {
    useJUnit()
    testLogging { events("passed", "failed", "skipped") }
}
