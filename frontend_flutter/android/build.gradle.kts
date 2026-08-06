import com.android.build.api.dsl.LibraryExtension

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

// Some legacy Flutter plugins still declare compileSdk 34 in their own
// Gradle file. The app and its transitive AndroidX dependencies require 36.
// Apply the installed SDK level after each library has finished configuring.
gradle.beforeProject {
    if (name == "file_picker") {
        afterEvaluate {
            extensions.findByType<LibraryExtension>()?.compileSdk = 36
        }
    }
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
