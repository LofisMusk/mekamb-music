pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "MekambMusicDesktop"

include(":shared")
include(":native-mac", ":native-linux", ":native-windows")
project(":native-mac").projectDir = file("../native-mac")
project(":native-linux").projectDir = file("../native-linux")
project(":native-windows").projectDir = file("../native-windows")
